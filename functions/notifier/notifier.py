import json
import boto3
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from decimal import Decimal
import html

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

# Environment variables
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')
REGION = os.environ.get('REGION', 'us-east-1')
FROM_EMAIL = os.environ.get('FROM_EMAIL')
TO_EMAIL = os.environ.get('TO_EMAIL')

# Email configuration from environment variables
EMAIL_SUBJECT_PREFIX = os.environ.get('EMAIL_SUBJECT_PREFIX', 'Data Analysis Report')
EMAIL_PRIORITY_ICON = os.environ.get('EMAIL_PRIORITY_ICON', '🚨')
EMAIL_WARNING_ICON = os.environ.get('EMAIL_WARNING_ICON', '⚠️')
EMAIL_SUCCESS_ICON = os.environ.get('EMAIL_SUCCESS_ICON', '✅')

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal objects from DynamoDB"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert decimal to int if it's a whole number, otherwise to float
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)

def convert_decimals(obj):
    """Recursively convert Decimal objects to int/float in nested structures"""
    if isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        # Convert decimal to int if it's a whole number, otherwise to float
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj

def lambda_handler(event, context):
    correlation_id = str(uuid.uuid4())
    
    try:
        log_event(correlation_id, 'notifier_triggered', {
            'message': 'Notifier lambda triggered',
            'event': event,
            'dynamodb_table': DYNAMODB_TABLE,
            'from_email': FROM_EMAIL,
            'to_email': TO_EMAIL
        })
        
        # Extract information from EventBridge event
        analysis_id = None
        if 'detail' in event:
            # EventBridge event
            detail = event['detail']
            analysis_id = detail.get('analysis_id')
            correlation_id = detail.get('correlation_id', correlation_id)
            insights_count = detail.get('insights_count', 0)
            anomalies_count = detail.get('anomalies_count', 0)
            high_value_anomalies = detail.get('high_value_anomalies', 0)
        else:
            # Direct invocation or test event
            analysis_id = event.get('analysis_id')
            insights_count = event.get('insights_count', 0)
            anomalies_count = event.get('anomalies_count', 0)
            high_value_anomalies = event.get('high_value_anomalies', 0)
        
        if not analysis_id:
            log_event(correlation_id, 'no_analysis_id', {
                'message': 'No analysis ID provided, cannot send notification'
            }, level='WARNING')
            return create_response(400, {
                'message': 'Analysis ID is required',
                'correlation_id': correlation_id
            })
        
        log_event(correlation_id, 'processing_notification', {
            'analysis_id': analysis_id,
            'insights_count': insights_count,
            'anomalies_count': anomalies_count,
            'high_value_anomalies': high_value_anomalies
        })
        
        # Retrieve full analysis details from DynamoDB
        analysis_details = get_analysis_details(analysis_id, correlation_id)
        
        if not analysis_details:
            log_event(correlation_id, 'analysis_not_found', {
                'message': 'Analysis not found in database',
                'analysis_id': analysis_id
            }, level='WARNING')
            return create_response(404, {
                'message': 'Analysis not found',
                'analysis_id': analysis_id,
                'correlation_id': correlation_id
            })
        
        # Send email notification
        email_sent = send_email_notification(analysis_details, correlation_id)
        
        if email_sent:
            # Update DynamoDB to mark notification as sent
            mark_notification_sent(analysis_id, correlation_id)
            
            log_event(correlation_id, 'notification_sent_successfully', {
                'analysis_id': analysis_id,
                'to_email': TO_EMAIL,
                'insights_count': len(analysis_details.get('insights', [])),
                'anomalies_count': len(analysis_details.get('anomalies', []))
            })
            
            return create_response(200, {
                'message': 'Email notification sent successfully',
                'analysis_id': analysis_id,
                'correlation_id': correlation_id,
                'email_sent_to': TO_EMAIL
            })
        else:
            return create_response(500, {
                'message': 'Failed to send email notification',
                'analysis_id': analysis_id,
                'correlation_id': correlation_id
            })
        
    except Exception as e:
        log_event(correlation_id, 'notification_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'analysis_id': analysis_id if 'analysis_id' in locals() else 'unknown'
        }, level='ERROR')
        
        return create_response(500, {
            'message': 'Error processing notification',
            'error': str(e),
            'correlation_id': correlation_id
        })

def log_event(correlation_id: str, event_type: str, details: Dict, level: str = 'INFO'):
    """Structured logging helper with Decimal handling"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'correlation_id': correlation_id,
        'event': event_type,
        'service': 'notifier',
        **convert_decimals(details)  # Convert Decimals before logging
    }
    
    if level == 'ERROR':
        logger.error(json.dumps(log_entry, cls=DecimalEncoder))
    elif level == 'WARNING':
        logger.warning(json.dumps(log_entry, cls=DecimalEncoder))
    else:
        logger.info(json.dumps(log_entry, cls=DecimalEncoder))

def create_response(status_code: int, body: Dict) -> Dict:
    """Create standardized Lambda response with Decimal handling"""
    return {
        'statusCode': status_code,
        'body': json.dumps(convert_decimals(body), cls=DecimalEncoder),
        'headers': {
            'Content-Type': 'application/json'
        }
    }

def get_analysis_details(analysis_id: str, correlation_id: str) -> Optional[Dict]:
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        
        response = table.get_item(
            Key={'analysis_id': analysis_id}
        )
        
        if 'Item' in response:
            # Convert Decimals to int/float before processing
            analysis_data = convert_decimals(response['Item'])
            
            log_event(correlation_id, 'analysis_retrieved', {
                'analysis_id': analysis_id,
                'insights_count': len(analysis_data.get('insights', [])),
                'anomalies_count': len(analysis_data.get('anomalies', [])),
                'records_analyzed': analysis_data.get('records_analyzed', 0),
                'analysis_timestamp': analysis_data.get('analysis_timestamp')
            })
            
            return analysis_data
        else:
            log_event(correlation_id, 'analysis_not_found_in_db', {
                'analysis_id': analysis_id,
                'table': DYNAMODB_TABLE
            }, level='WARNING')
            return None
            
    except Exception as e:
        log_event(correlation_id, 'dynamodb_retrieval_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'analysis_id': analysis_id,
            'table': DYNAMODB_TABLE
        }, level='ERROR')
        return None

def send_email_notification(analysis_details: Dict, correlation_id: str) -> bool:
    """Send formatted email notification using Amazon SES"""
    try:
        # Ensure analysis_details doesn't contain Decimals
        analysis_details = convert_decimals(analysis_details)
        
        # Generate email content
        subject = generate_email_subject(analysis_details)
        html_body = generate_html_email_body(analysis_details)
        
        log_event(correlation_id, 'sending_email', {
            'analysis_id': analysis_details.get('analysis_id'),
            'from_email': FROM_EMAIL,
            'to_email': TO_EMAIL,
            'subject': subject,
            'html_body_length': len(html_body)
        })
        
        # Validate email addresses
        if not FROM_EMAIL or not TO_EMAIL:
            raise ValueError("FROM_EMAIL and TO_EMAIL must be configured")
        
        # Send email via SES
        response = ses_client.send_email(
            Source=FROM_EMAIL,
            Destination={
                'ToAddresses': [TO_EMAIL]
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': html_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        
        message_id = response.get('MessageId')
        log_event(correlation_id, 'email_sent_successfully', {
            'message_id': message_id,
            'analysis_id': analysis_details.get('analysis_id'),
            'email_length': len(html_body)
        })
        
        return True
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        log_event(correlation_id, 'ses_client_error', {
            'error': str(e),
            'error_code': error_code,
            'from_email': FROM_EMAIL,
            'to_email': TO_EMAIL
        }, level='ERROR')
        return False
    except Exception as e:
        log_event(correlation_id, 'email_send_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'analysis_id': analysis_details.get('analysis_id')
        }, level='ERROR')
        return False

def generate_email_subject(analysis_details: Dict) -> str:
    """Generate email subject line based on analysis results"""
    analysis_id = analysis_details.get('analysis_id', 'Unknown')
    anomalies_count = len(analysis_details.get('anomalies', []))
    
    # Check for high severity anomalies
    high_severity_anomalies = [
        anomaly for anomaly in analysis_details.get('anomalies', [])
        if anomaly.get('severity', '').lower() == 'high'
    ]
    
    if high_severity_anomalies:
        return f"{EMAIL_PRIORITY_ICON} ALERT: {EMAIL_SUBJECT_PREFIX} - High Priority Anomalies Detected ({analysis_id})"
    elif anomalies_count > 0:
        return f"{EMAIL_WARNING_ICON} {EMAIL_SUBJECT_PREFIX} - Anomalies Detected ({analysis_id})"
    else:
        return f"{EMAIL_SUCCESS_ICON} {EMAIL_SUBJECT_PREFIX} - All Normal ({analysis_id})"

def generate_html_email_body(analysis_details: Dict) -> str:
    """Generate HTML email body with formatted analysis results"""
    # Ensure no Decimals in the data
    analysis_details = convert_decimals(analysis_details)
    
    analysis_id = analysis_details.get('analysis_id', 'Unknown')
    correlation_id = analysis_details.get('correlation_id', 'Unknown')
    source_file = analysis_details.get('source_file', 'Unknown')
    processed_file = analysis_details.get('processed_file', 'Unknown')
    records_analyzed = analysis_details.get('records_analyzed', 0)
    analysis_timestamp = analysis_details.get('analysis_timestamp', datetime.utcnow().isoformat())
    summary = html.escape(str(analysis_details.get('summary', 'No summary available')))
    
    insights = analysis_details.get('insights', [])
    anomalies = analysis_details.get('anomalies', [])
    recommendations = analysis_details.get('recommendations', [])
    
    # Determine status and priority
    high_severity_anomalies = [a for a in anomalies if a.get('severity', '').lower() == 'high']
    status_icon = EMAIL_PRIORITY_ICON if high_severity_anomalies else EMAIL_WARNING_ICON if anomalies else EMAIL_SUCCESS_ICON
    status_text = "HIGH PRIORITY" if high_severity_anomalies else "ATTENTION NEEDED" if anomalies else "NORMAL"
    status_color = "#dc3545" if high_severity_anomalies else "#ffc107" if anomalies else "#28a745"
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{EMAIL_SUBJECT_PREFIX}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: {status_color}; color: white; padding: 20px; border-radius: 8px; text-align: center; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .insight {{ background-color: #e8f4fd; padding: 10px; margin: 5px 0; border-radius: 4px; }}
        .anomaly {{ background-color: #fff3cd; padding: 10px; margin: 5px 0; border-radius: 4px; }}
        .anomaly.high {{ background-color: #f8d7da; border-left: 4px solid #dc3545; }}
        .recommendation {{ background-color: #d1ecf1; padding: 10px; margin: 5px 0; border-radius: 4px; }}
        .metadata {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; font-size: 0.9em; }}
        .badge {{ display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }}
        .badge.high {{ background-color: #dc3545; color: white; }}
        .badge.medium {{ background-color: #ffc107; color: black; }}
        .badge.low {{ background-color: #28a745; color: white; }}
        .stats {{ display: flex; justify-content: space-around; margin: 20px 0; }}
        .stat {{ text-align: center; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: {status_color}; }}
        .stat-label {{ font-size: 0.9em; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{status_icon} {EMAIL_SUBJECT_PREFIX}</h1>
            <h2>Status: {status_text}</h2>
            <p>Analysis ID: {analysis_id}</p>
        </div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-number">{len(insights)}</div>
                <div class="stat-label">Insights</div>
            </div>
            <div class="stat">
                <div class="stat-number">{len(anomalies)}</div>
                <div class="stat-label">Anomalies</div>
            </div>
            <div class="stat">
                <div class="stat-number">{records_analyzed:,}</div>
                <div class="stat-label">Records Analyzed</div>
            </div>
        </div>
        
        <div class="section">
            <h3>📊 Analysis Summary</h3>
            <p>{summary}</p>
        </div>
    """
    
    # Add insights section
    if insights:
        html_body += f"""
        <div class="section">
            <h3>💡 Key Insights ({len(insights)})</h3>
        """
        for insight in insights:
            confidence = insight.get('confidence', 'medium')
            insight_type = html.escape(str(insight.get('type', 'General')))
            description = html.escape(str(insight.get('description', 'No description')))
            
            html_body += f"""
            <div class="insight">
                <strong>{insight_type.replace('_', ' ').title()}</strong> 
                <span class="badge {confidence}">{confidence.upper()}</span>
                <br>{description}
            </div>
            """
        html_body += "</div>"
    
    # Add anomalies section
    if anomalies:
        html_body += f"""
        <div class="section">
            <h3>⚠️ Anomalies Detected ({len(anomalies)})</h3>
        """
        for anomaly in anomalies:
            severity = anomaly.get('severity', 'medium').lower()
            anomaly_type = html.escape(str(anomaly.get('type', 'General')))
            description = html.escape(str(anomaly.get('description', 'No description')))
            
            html_body += f"""
            <div class="anomaly {severity}">
                <strong>{anomaly_type.replace('_', ' ').title()}</strong> 
                <span class="badge {severity}">{severity.upper()}</span>
                <br>{description}
            </div>
            """
        html_body += "</div>"
    
    # Add recommendations section
    if recommendations:
        html_body += f"""
        <div class="section">
            <h3>🎯 Recommendations ({len(recommendations)})</h3>
        """
        for rec in recommendations:
            category = html.escape(str(rec.get('category', 'General')))
            action = html.escape(str(rec.get('action', 'No action specified')))
            priority = rec.get('priority', 'medium')
            
            html_body += f"""
            <div class="recommendation">
                <strong>{category.title()}</strong> 
                <span class="badge {priority}">{priority.upper()}</span>
                <br>{action}
            </div>
            """
        html_body += "</div>"
    
    # Add metadata section
    html_body += f"""
        <div class="metadata">
            <h4>📋 Analysis Metadata</h4>
            <p><strong>Analysis ID:</strong> {analysis_id}</p>
            <p><strong>Correlation ID:</strong> {correlation_id}</p>
            <p><strong>Source File:</strong> {source_file}</p>
            <p><strong>Processed File:</strong> {processed_file}</p>
            <p><strong>Records Analyzed:</strong> {records_analyzed:,}</p>
            <p><strong>Analysis Timestamp:</strong> {analysis_timestamp}</p>
            <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
        
        <div class="section" style="text-align: center; color: #666; font-size: 0.9em;">
            <p>This is an automated notification from the Serverless Data Processing Pipeline.</p>
            <p>For questions or support, please contact the data team.</p>
        </div>
    </div>
</body>
</html>
    """
    
    return html_body

def mark_notification_sent(analysis_id: str, correlation_id: str):
    """Update DynamoDB record to mark notification as sent"""
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        
        table.update_item(
            Key={'analysis_id': analysis_id},
            UpdateExpression='SET notification_sent = :sent, notification_timestamp = :timestamp',
            ExpressionAttributeValues={
                ':sent': True,
                ':timestamp': datetime.utcnow().isoformat()
            }
        )
        
        log_event(correlation_id, 'notification_status_updated', {
            'analysis_id': analysis_id,
            'table': DYNAMODB_TABLE
        })
        
    except Exception as e:
        log_event(correlation_id, 'notification_update_error', {
            'error': str(e),
            'analysis_id': analysis_id
        }, level='WARNING')