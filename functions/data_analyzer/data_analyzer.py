import json
import boto3
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
import csv
from io import StringIO
from botocore.exceptions import ClientError
import time

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock_client = boto3.client('bedrock-runtime')
eventbridge_client = boto3.client('events')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')
REGION = os.environ.get('REGION', 'us-east-1')
EVENT_BUS_NAME = os.environ.get('EVENT_BUS_NAME', 'default')

def lambda_handler(event, context):
    """
    Lambda function to analyze processed data using Amazon Bedrock.
    Triggered by EventBridge when processing is complete.
    """
    correlation_id = str(uuid.uuid4())
    
    try:
        log_event(correlation_id, 'analyzer_triggered', {
            'message': 'Data analyzer lambda triggered',
            'event': event
        })
        
        # Extract information from EventBridge event
        if 'detail' in event:
            # EventBridge custom event
            detail = event['detail']
            processed_file = detail.get('processed_file')
            source_file = detail.get('source_file')
            valid_records_count = detail.get('valid_records', 0)
            correlation_id = detail.get('correlation_id', correlation_id)
        else:
            # Direct invocation or test event
            processed_file = event.get('processed_file')
            source_file = event.get('source_file')
            valid_records_count = event.get('valid_records', 0)
        
        if not processed_file:
            log_event(correlation_id, 'no_processed_file', {
                'message': 'No processed file specified, skipping analysis'
            }, level='WARNING')
            return create_response(200, {
                'message': 'No processed file to analyze',
                'correlation_id': correlation_id
            })
        
        log_event(correlation_id, 'analyzing_file', {
            'processed_file': processed_file,
            'source_file': source_file,
            'valid_records_count': valid_records_count
        })
        
        # Download and analyze processed data
        processed_data = download_processed_data(processed_file, correlation_id)
        
        if not processed_data:
            log_event(correlation_id, 'no_data_found', {
                'message': 'No data found in processed file'
            }, level='WARNING')
            return create_response(200, {
                'message': 'No data to analyze',
                'correlation_id': correlation_id
            })
        
        # Perform Bedrock analysis
        analysis_results = analyze_with_bedrock(processed_data, correlation_id)
        
        # Store results in DynamoDB
        analysis_id = store_analysis_results(
            analysis_results, processed_file, source_file, 
            len(processed_data), correlation_id
        )
        
        # Publish analysis complete event
        publish_analysis_complete_event(analysis_id, analysis_results, correlation_id)
        
        log_event(correlation_id, 'analysis_complete', {
            'analysis_id': analysis_id,
            'processed_file': processed_file,
            'records_analyzed': len(processed_data),
            'insights_generated': len(analysis_results.get('insights', []))
        })
        
        return create_response(200, {
            'message': 'Analysis completed successfully',
            'correlation_id': correlation_id,
            'analysis_id': analysis_id,
            'records_analyzed': len(processed_data),
            'insights_count': len(analysis_results.get('insights', []))
        })
        
    except Exception as e:
        log_event(correlation_id, 'analysis_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'processed_file': processed_file if 'processed_file' in locals() else 'unknown'
        }, level='ERROR')
        
        return create_response(500, {
            'message': 'Error analyzing data',
            'error': str(e),
            'correlation_id': correlation_id
        })

def log_event(correlation_id: str, event_type: str, details: Dict, level: str = 'INFO'):
    """Structured logging helper"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'correlation_id': correlation_id,
        'event': event_type,
        'service': 'data-analyzer',
        **details
    }
    
    if level == 'ERROR':
        logger.error(json.dumps(log_entry))
    elif level == 'WARNING':
        logger.warning(json.dumps(log_entry))
    else:
        logger.info(json.dumps(log_entry))

def create_response(status_code: int, body: Dict) -> Dict:
    """Create standardized Lambda response"""
    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {
            'Content-Type': 'application/json'
        }
    }

def download_processed_data(processed_file: str, correlation_id: str) -> List[Dict]:
    """Download processed data from S3"""
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=processed_file)
        file_content = response['Body'].read().decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.DictReader(StringIO(file_content))
        data = list(csv_reader)
        
        log_event(correlation_id, 'data_downloaded', {
            'file': processed_file,
            'records_count': len(data)
        })
        
        return data
        
    except Exception as e:
        log_event(correlation_id, 'download_error', {
            'error': str(e),
            'file': processed_file
        }, level='ERROR')
        raise

def analyze_with_bedrock(data: List[Dict], correlation_id: str) -> Dict:
    """Analyze data using Amazon Bedrock"""
    try:
        # Prepare data summary for analysis
        data_summary = prepare_data_summary(data)
        
        # Create prompt for Bedrock
        prompt = create_analysis_prompt(data_summary)
        
        log_event(correlation_id, 'calling_bedrock', {
            'model': 'anthropic.claude-3-sonnet-20240229-v1:0',
            'data_records': len(data)
        })
        
        # Call Bedrock
        response = bedrock_client.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }),
            contentType='application/json'
        )
        
        # Parse Bedrock response
        result = json.loads(response['body'].read())
        analysis_text = result['content'][0]['text']
        
        # Parse the structured analysis
        analysis_results = parse_bedrock_response(analysis_text, correlation_id)
        
        log_event(correlation_id, 'bedrock_analysis_complete', {
            'insights_generated': len(analysis_results.get('insights', [])),
            'anomalies_detected': len(analysis_results.get('anomalies', []))
        })
        
        return analysis_results
        
    except Exception as e:
        log_event(correlation_id, 'bedrock_error', {
            'error': str(e),
            'error_type': type(e).__name__
        }, level='ERROR')
        
        # Fallback to basic analysis if Bedrock fails
        return perform_basic_analysis(data, correlation_id)

def prepare_data_summary(data: List[Dict]) -> Dict:
    """Prepare a summary of the data for analysis"""
    if not data:
        return {}
    
    # Calculate basic statistics
    total_records = len(data)
    brands = {}
    regions = {}
    price_values = []
    
    for record in data:
        # Brand analysis
        brand = record.get('brand', 'Unknown')
        brands[brand] = brands.get(brand, 0) + 1
        
        # Region analysis
        region = record.get('region', 'Unknown')
        regions[region] = regions.get(region, 0) + 1
        
        # Price analysis
        try:
            price = float(record.get('price', 0))
            price_values.append(price)
        except (ValueError, TypeError):
            continue
    
    # Calculate price statistics
    price_stats = {}
    if price_values:
        price_stats = {
            'min': min(price_values),
            'max': max(price_values),
            'avg': sum(price_values) / len(price_values),
            'total': sum(price_values)
        }
    
    return {
        'total_records': total_records,
        'top_brands': dict(sorted(brands.items(), key=lambda x: x[1], reverse=True)[:5]),
        'regions': regions,
        'price_statistics': price_stats,
        'sample_records': data[:3] if len(data) > 3 else data
    }

def create_analysis_prompt(data_summary: Dict) -> str:
    """Create a prompt for Bedrock analysis"""
    return f"""
Analyze the following smartphone sales data and provide insights in JSON format:

Data Summary:
- Total Records: {data_summary.get('total_records', 0)}
- Top Brands: {data_summary.get('top_brands', {})}
- Regions: {data_summary.get('regions', {})}
- Price Statistics: {data_summary.get('price_statistics', {})}

Sample Records:
{json.dumps(data_summary.get('sample_records', []), indent=2)}

Please provide your analysis in the following JSON format:
{{
  "insights": [
    {{
      "type": "market_trend",
      "description": "Description of the insight",
      "confidence": "high/medium/low"
    }}
  ],
  "anomalies": [
    {{
      "type": "price_anomaly",
      "description": "Description of the anomaly",
      "severity": "high/medium/low"
    }}
  ],
  "recommendations": [
    {{
      "category": "pricing/inventory/marketing",
      "action": "Recommended action",
      "priority": "high/medium/low"
    }}
  ],
  "summary": "Brief summary of key findings"
}}

Focus on:
1. Price trends and anomalies
2. Regional sales patterns
3. Brand performance
4. Potential business opportunities
5. Any unusual patterns in the data
"""

def parse_bedrock_response(analysis_text: str, correlation_id: str) -> Dict:
    """Parse Bedrock response into structured format"""
    try:
        # Try to extract JSON from the response
        start_idx = analysis_text.find('{')
        end_idx = analysis_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx != -1:
            json_str = analysis_text[start_idx:end_idx]
            return json.loads(json_str)
        else:
            # Fallback: create structured response from text
            return {
                'insights': [
                    {
                        'type': 'general_analysis',
                        'description': analysis_text[:500],
                        'confidence': 'medium'
                    }
                ],
                'anomalies': [],
                'recommendations': [],
                'summary': 'Analysis completed with text response'
            }
            
    except Exception as e:
        log_event(correlation_id, 'response_parsing_error', {
            'error': str(e),
            'response_length': len(analysis_text)
        }, level='WARNING')
        
        return {
            'insights': [
                {
                    'type': 'analysis_error',
                    'description': 'Failed to parse Bedrock response',
                    'confidence': 'low'
                }
            ],
            'anomalies': [],
            'recommendations': [],
            'summary': 'Analysis completed with parsing errors'
        }

def perform_basic_analysis(data: List[Dict], correlation_id: str) -> Dict:
    """Perform basic analysis as fallback"""
    try:
        data_summary = prepare_data_summary(data)
        
        insights = []
        anomalies = []
        recommendations = []
        
        # Basic insights
        if data_summary.get('price_statistics'):
            price_stats = data_summary['price_statistics']
            insights.append({
                'type': 'price_analysis',
                'description': f"Average price: ${price_stats['avg']:.2f}, Range: ${price_stats['min']:.2f} - ${price_stats['max']:.2f}",
                'confidence': 'high'
            })
        
        # Check for high-value transactions
        high_value_threshold = 1000
        if data_summary.get('price_statistics', {}).get('max', 0) > high_value_threshold:
            anomalies.append({
                'type': 'high_value_transaction',
                'description': f"High-value transaction detected: ${data_summary['price_statistics']['max']:.2f}",
                'severity': 'medium'
            })
        
        return {
            'insights': insights,
            'anomalies': anomalies,
            'recommendations': recommendations,
            'summary': f"Basic analysis completed for {len(data)} records"
        }
        
    except Exception as e:
        log_event(correlation_id, 'basic_analysis_error', {
            'error': str(e)
        }, level='ERROR')
        
        return {
            'insights': [],
            'anomalies': [],
            'recommendations': [],
            'summary': 'Analysis failed'
        }

def store_analysis_results(analysis_results: Dict, processed_file: str, 
                         source_file: str, records_count: int, correlation_id: str) -> str:
    """Store analysis results in DynamoDB"""
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        analysis_id = f"analysis_{int(datetime.utcnow().timestamp())}_{correlation_id[:8]}"
        
        item = {
            'analysis_id': analysis_id,
            'correlation_id': correlation_id,
            'processed_file': processed_file,
            'source_file': source_file,
            'records_analyzed': records_count,
            'analysis_timestamp': datetime.utcnow().isoformat(),
            'insights': analysis_results.get('insights', []),
            'anomalies': analysis_results.get('anomalies', []),
            'recommendations': analysis_results.get('recommendations', []),
            'summary': analysis_results.get('summary', ''),
            'ttl': int((datetime.utcnow().timestamp()) + (30 * 24 * 60 * 60))  # 30 days TTL
        }
        
        table.put_item(Item=item)
        
        log_event(correlation_id, 'results_stored', {
            'analysis_id': analysis_id,
            'table': DYNAMODB_TABLE
        })
        
        return analysis_id
        
    except Exception as e:
        log_event(correlation_id, 'storage_error', {
            'error': str(e),
            'table': DYNAMODB_TABLE
        }, level='ERROR')
        raise

def publish_analysis_complete_event(analysis_id: str, analysis_results: Dict, correlation_id: str):
    """Publish analysis complete event to EventBridge"""
    try:
        # Check for conditions that should trigger notifications
        high_value_anomalies = [
            anomaly for anomaly in analysis_results.get('anomalies', [])
            if 'high_value' in anomaly.get('type', '').lower() or 
               anomaly.get('severity') == 'high'
        ]
        
        event_detail = {
            'analysis_id': analysis_id,
            'correlation_id': correlation_id,
            'insights_count': len(analysis_results.get('insights', [])),
            'anomalies_count': len(analysis_results.get('anomalies', [])),
            'high_value_anomalies': len(high_value_anomalies),
            'summary': analysis_results.get('summary', ''),
            'notification_required': len(high_value_anomalies) > 0
        }
        
        eventbridge_client.put_events(
            Entries=[
                {
                    'Source': 'madhu.data-processing',
                    'DetailType': 'Analysis Complete',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': EVENT_BUS_NAME
                }
            ]
        )
        
        log_event(correlation_id, 'event_published', {
            'event_type': 'Analysis Complete',
            'analysis_id': analysis_id,
            'notification_required': event_detail['notification_required']
        })
        
    except Exception as e:
        log_event(correlation_id, 'event_publish_error', {
            'error': str(e),
            'analysis_id': analysis_id
        }, level='WARNING')