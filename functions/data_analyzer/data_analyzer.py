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

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock_client = boto3.client('bedrock-runtime')
eventbridge_client = boto3.client('events')

BUCKET_NAME = os.environ.get('BUCKET_NAME')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')
REGION = os.environ.get('REGION', 'us-east-1')
EVENT_BUS_NAME = os.environ.get('EVENT_BUS_NAME', 'default')

BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID')
BEDROCK_MAX_TOKENS = os.environ.get('BEDROCK_MAX_TOKENS')

def lambda_handler(event, context):
    correlation_id = str(uuid.uuid4())
    
    try:
        log_event(correlation_id, 'analyzer_triggered', {
            'message': 'Data analyzer lambda triggered',
            'event': event
        })
        
        # Extract information from EventBridge
        if 'detail' in event:
            detail = event['detail']
            processed_file = detail.get('processed_file')
            source_file = detail.get('source_file')
            valid_records_count = detail.get('valid_records', 0)
            correlation_id = detail.get('correlation_id', correlation_id)
        else:
            raise ValueError("Invalid event format: 'detail' key missing")
        
        if not processed_file:
            raise ValueError("Processed file key missing in event detail")
        
        log_event(correlation_id, 'analyzing_file', {
            'processed_file': processed_file,
            'source_file': source_file,
            'valid_records_count': valid_records_count
        })
        
        processed_data = download_processed_data(processed_file, correlation_id)
        
        if not processed_data:
            raise ValueError("No data found in processed file")
        
        analysis_results = analyze_with_bedrock(processed_data, correlation_id)

        if not analysis_results:
            raise ValueError("Analysis failed or returned no results")

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
    try:
        prompt = create_analysis_prompt(data)

        log_event(correlation_id, 'calling_bedrock', {
            'model': BEDROCK_MODEL_ID,
            'data_records': len(data)
        })

        body = {
            "system": [
                {"text": "You are a data analysis assistant. Provide insights, detect anomalies, and suggest recommendations based on the provided data."}
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"text": prompt}
                    ]
                }
            ],
            "inferenceConfig": {
                "maxTokens": int(BEDROCK_MAX_TOKENS ),
                "temperature": 1.0,
                "topP": 0.9
            }
        }

        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            contentType='application/json'
        )

        result = json.loads(response['body'].read())

        message_content = result.get("output", {}).get("message", {}).get("content", [])
        if not message_content:
            raise ValueError(f"No content in Bedrock response: {result}")

        # Extract text segments
        analysis_text_parts = [
            c.get("text", "") for c in message_content if "text" in c
        ]
        analysis_text = "\n".join(analysis_text_parts)

        # Parse to structured analysis
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
        return None

def create_analysis_prompt(data: List[Dict]) -> str:

    max_records = 1000
    if len(data) > max_records:
        data = data[:max_records]
    
    data_json = json.dumps(data, indent=2)
    
    return f"""
You are a smartphone market analysis expert.

Analyze the following smartphone sales dataset with focus on customer reviews and market segments. Provide insights in JSON format.

The dataset contains sales records with fields including model, brand, price, customer_review, and region. Your job is to:
- Analyze customer sentiment from reviews to identify most positively reviewed phones
- Determine the most purchased/popular phone models based on sales frequency
- Categorize phones into price segments: Budget (<$500), Mid-range ($500-$1000), Flagship (>$1000)
- Provide targeted recommendations for each price segment

Here is the dataset:
{data_json}

Please respond ONLY with a JSON object in the following format:

{{
  "insights": [
    {{
      "type": "most_popular_phone",
      "description": "The most frequently purchased phone model with sales count",
      "confidence": "high/medium/low"
    }},
    {{
      "type": "customer_satisfaction",
      "description": "Analysis of customer reviews and satisfaction trends by brand/model",
      "confidence": "high/medium/low"
    }},
    {{
      "type": "price_segment_performance",
      "description": "Performance analysis across budget, mid-range, and flagship segments",
      "confidence": "high/medium/low"
    }}
  ],
  "anomalies": [
    {{
      "type": "review_anomaly",
      "description": "Unusual patterns in customer reviews or satisfaction",
      "severity": "high/medium/low"
    }},
    {{
      "type": "price_anomaly", 
      "description": "Phones with pricing that doesn't match their segment expectations",
      "severity": "high/medium/low"
    }}
  ],
  "recommendations": [
    {{
      "category": "budget_segment",
      "action": "Top 2 recommended budget phones (<$500) based on customer reviews and sales",
      "priority": "high/medium/low"
    }},
    {{
      "category": "midrange_segment", 
      "action": "Top 2 recommended mid-range phones ($500-$1000) based on customer reviews and sales",
      "priority": "high/medium/low"
    }},
    {{
      "category": "flagship_segment",
      "action": "Top 2 recommended flagship phones (>$1000) based on customer reviews and sales", 
      "priority": "high/medium/low"
    }},
    {{
      "category": "inventory_strategy",
      "action": "Inventory recommendations based on popular models and positive reviews",
      "priority": "high/medium/low"
    }}
  ],
  "summary": "Brief summary focusing on most popular phones, customer satisfaction trends, and segment-wise recommendations"
}}

Focus on:
- Customer review sentiment analysis to identify highly rated phones
- Sales frequency to determine most popular models
- Price segment analysis (Budget: <$500, Mid-range: $500-$1000, Flagship: >$1000)
- Customer satisfaction patterns by brand and model
- Regional preferences and trends
- Value-for-money assessment based on price vs customer satisfaction

Avoid explaining the JSON format. Only return the structured output.
"""


def parse_bedrock_response(analysis_text: str, correlation_id: str) -> Dict:
    try:
        # Try to extract JSON from the response
        start_idx = analysis_text.find('{')
        end_idx = analysis_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx != -1:
            json_str = analysis_text[start_idx:end_idx]
            return json.loads(json_str)
        else:
            raise ValueError("No JSON object found in Bedrock response")
            
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

def store_analysis_results(analysis_results: Dict, processed_file: str, 
                         source_file: str, records_count: int, correlation_id: str) -> str:

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
            'summary': analysis_results.get('summary', '')
        }
        
        # Publish event to EventBridge
        response = eventbridge_client.put_events(
            Entries=[
                {
                    'Source': 'madhu.data-processing',
                    'DetailType': 'Analysis Complete',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': EVENT_BUS_NAME,
                    'Time': datetime.utcnow()
                }
            ]
        )
        
        # Check if event was published successfully
        failed_entries = response.get('FailedEntryCount', 0)
        if failed_entries > 0:
            raise Exception(f"Failed to publish {failed_entries} events to EventBridge")
        
        log_event(correlation_id, 'analysis_event_published', {
            'event_type': 'Analysis Complete',
            'event_bus': EVENT_BUS_NAME,
            'analysis_id': analysis_id,
            'event_id': response['Entries'][0].get('EventId') if response.get('Entries') else None
        })
        
    except Exception as e:
        log_event(correlation_id, 'analysis_event_publish_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'event_bus': EVENT_BUS_NAME,
            'analysis_id': analysis_id
        }, level='ERROR')
