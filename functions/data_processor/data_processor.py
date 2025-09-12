import json
import boto3
import csv
import logging
import os
import hashlib
from datetime import datetime
from typing import Dict, List, Tuple
import uuid
from io import StringIO
from botocore.exceptions import ClientError
import time

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients with retry configuration
s3_client = boto3.client('s3', 
    config=boto3.session.Config(
        retries={'max_attempts': 3, 'mode': 'adaptive'}
    )
)

# Initialize EventBridge client
eventbridge_client = boto3.client('events')

# Get environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME')
REGION = os.environ.get('REGION', 'us-east-1')
EVENT_BUS_NAME = os.environ.get('EVENT_BUS_NAME', 'default')

def lambda_handler(event, context):

    correlation_id = str(uuid.uuid4())
    
    try:
        # Log the incoming event with structured format
        log_event(correlation_id, 'lambda_triggered', {
            'message': 'Data processor lambda triggered',
            'bucket_name': BUCKET_NAME,
            'region': REGION,
            'event_bus_name': EVENT_BUS_NAME,
            'lambda_request_id': context.aws_request_id if context else None
        })
        
        # Extract S3 event information
        if not event.get('Records'):
            raise ValueError("No S3 records found in event")
            
        record = event['Records'][0]
        bucket_name = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']
        object_etag = record['s3']['object'].get('eTag', '').strip('"')
        
        # Validate that the file is in the input/ folder
        if not object_key.startswith('input/'):
            log_event(correlation_id, 'invalid_location', {
                'message': 'File not in input/ folder, skipping processing',
                'object_key': object_key
            }, level='WARNING')
            return create_response(200, {
                'message': 'File not in input folder, skipping',
                'correlation_id': correlation_id
            })
        
        # Check for idempotency - has this file been processed already?
        if is_already_processed(bucket_name, object_key, object_etag, correlation_id):
            log_event(correlation_id, 'duplicate_processing_skipped', {
                'message': 'File already processed, skipping',
                'object_key': object_key,
                'etag': object_etag
            })
            return create_response(200, {
                'message': 'File already processed, skipping duplicate',
                'correlation_id': correlation_id
            })
        
        log_event(correlation_id, 'processing_file', {
            'bucket': bucket_name,
            'object_key': object_key,
            'etag': object_etag
        })
        
        # Download and process the file with retries
        valid_records, invalid_records = process_csv_file_with_retry(
            bucket_name, object_key, correlation_id
        )
        
        # Upload processed data to appropriate folders with retries
        processed_files = upload_results_with_retry(
            bucket_name, object_key, valid_records, invalid_records, 
            correlation_id, object_etag
        )
        
        # Publish EventBridge event to trigger next stage (data analyzer)
        publish_processing_complete_event(
            processed_files, object_key, len(valid_records), 
            len(invalid_records), correlation_id
        )
        
        # Log summary
        log_event(correlation_id, 'processing_complete', {
            'total_valid_records': len(valid_records),
            'total_invalid_records': len(invalid_records),
            'source_file': object_key,
            'valid_percentage': round(
                (len(valid_records) / (len(valid_records) + len(invalid_records))) * 100, 2
            ) if (len(valid_records) + len(invalid_records)) > 0 else 0,
            'processed_files': processed_files
        })
        
        return create_response(200, {
            'message': 'File processed successfully',
            'correlation_id': correlation_id,
            'valid_records': len(valid_records),
            'invalid_records': len(invalid_records),
            'source_file': object_key,
            **processed_files
        })
        
    except Exception as e:
        log_event(correlation_id, 'processing_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'object_key': object_key if 'object_key' in locals() else 'unknown'
        }, level='ERROR')
        
        return create_response(500, {
            'message': 'Error processing file',
            'error': str(e),
            'correlation_id': correlation_id
        })

def publish_processing_complete_event(processed_files: Dict, source_file: str, 
                                    valid_count: int, invalid_count: int, correlation_id: str):

    try:
        # Only trigger analysis if there are valid records
        if valid_count == 0:
            log_event(correlation_id, 'no_analysis_needed', {
                'message': 'No valid records found, skipping analysis trigger',
                'source_file': source_file,
                'invalid_count': invalid_count
            }, level='WARNING')
            return
        
        # Create event detail with all necessary information for the analyzer
        event_detail = {
            'correlation_id': correlation_id,
            'source_file': source_file,
            'processed_file': processed_files.get('processed_file'),
            'rejected_file': processed_files.get('rejected_file'),
            'valid_records': valid_count,
            'invalid_records': invalid_count,
            'processing_timestamp': datetime.utcnow().isoformat(),
            'bucket_name': BUCKET_NAME,
            'region': REGION,
            'trigger_analysis': True,
            'data_quality_score': round((valid_count / (valid_count + invalid_count)) * 100, 2) if (valid_count + invalid_count) > 0 else 0
        }
        
        # Publish event to EventBridge
        response = eventbridge_client.put_events(
            Entries=[
                {
                    'Source': 'madhu.data-processing',
                    'DetailType': 'Processing Complete',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': EVENT_BUS_NAME,
                    'Time': datetime.utcnow()
                }
            ]
        )
        
        # Check if event was published successfully
        failed_entries = response.get('FailedEntryCount', 0)
        if failed_entries > 0:
            log_event(correlation_id, 'event_publish_failed', {
                'failed_entries': failed_entries,
                'failures': response.get('Entries', [])
            }, level='ERROR')
            raise Exception(f"Failed to publish {failed_entries} events to EventBridge")
        
        log_event(correlation_id, 'processing_event_published', {
            'event_type': 'Processing Complete',
            'event_bus': EVENT_BUS_NAME,
            'valid_records': valid_count,
            'invalid_records': invalid_count,
            'processed_file': processed_files.get('processed_file'),
            'data_quality_score': event_detail['data_quality_score'],
            'event_id': response['Entries'][0].get('EventId') if response.get('Entries') else None
        })
        
    except Exception as e:
        log_event(correlation_id, 'event_publish_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'event_bus': EVENT_BUS_NAME,
            'source_file': source_file
        }, level='ERROR')

def log_event(correlation_id: str, event_type: str, details: Dict, level: str = 'INFO'):

    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'correlation_id': correlation_id,
        'event': event_type,
        'service': 'data-processor',
        **details
    }
    
    if level == 'ERROR':
        logger.error(json.dumps(log_entry))
    elif level == 'WARNING':
        logger.warning(json.dumps(log_entry))
    else:
        logger.info(json.dumps(log_entry))

def create_response(status_code: int, body: Dict) -> Dict:

    return {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {
            'Content-Type': 'application/json'
        }
    }

def is_already_processed(bucket_name: str, object_key: str, object_etag: str, correlation_id: str) -> bool:
    """
    Check if file has already been processed by looking for processed output.
    Idempotency check based on source file metadata.
    """
    try:
        base_filename = object_key.split('/')[-1].replace('.csv', '')
        if base_filename == 'bad':
            raise Exception("Intentional test error for CloudWatch alert")
    
        # Check if processed files exist with matching source metadata
        processed_prefix = f"processed/{base_filename}_processed_"
        rejected_prefix = f"rejected/{base_filename}_rejected_"
        
        for prefix in [processed_prefix, rejected_prefix]:
            try:
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    Prefix=prefix,
                    MaxKeys=10
                )
                
                if response.get('Contents'):
                    # Check metadata of existing processed files
                    for obj in response['Contents']:
                        try:
                            head_response = s3_client.head_object(
                                Bucket=bucket_name, 
                                Key=obj['Key']
                            )
                            
                            metadata = head_response.get('Metadata', {})
                            if metadata.get('source-etag') == object_etag:
                                return True
                        except ClientError:
                            continue
                            
            except ClientError:
                continue
                
        return False
        
    except Exception as e:
        log_event(correlation_id, 'idempotency_check_error', {
            'error': str(e),
            'object_key': object_key
        }, level='WARNING')
        return False

def process_csv_file_with_retry(bucket_name: str, object_key: str, correlation_id: str, max_retries: int = 3) -> Tuple[List[Dict], List[Dict]]:

    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return process_csv_file(bucket_name, object_key, correlation_id)
        except ClientError as e:
            last_exception = e
            error_code = e.response.get('Error', {}).get('Code', '')
            
            if error_code in ['NoSuchKey', 'AccessDenied']:
                # Don't retry for these errors
                raise
            
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + 1  # Exponential backoff
                log_event(correlation_id, 'retrying_file_processing', {
                    'attempt': attempt + 1,
                    'max_retries': max_retries,
                    'wait_time': wait_time,
                    'error': str(e)
                }, level='WARNING')
                time.sleep(wait_time)
            else:
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + 1
                log_event(correlation_id, 'retrying_file_processing', {
                    'attempt': attempt + 1,
                    'max_retries': max_retries,
                    'wait_time': wait_time,
                    'error': str(e)
                }, level='WARNING')
                time.sleep(wait_time)
                last_exception = e
            else:
                raise
    
    raise last_exception

def process_csv_file(bucket_name: str, object_key: str, correlation_id: str) -> Tuple[List[Dict], List[Dict]]:

    try:
        # Download file from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read().decode('utf-8')
        
        log_event(correlation_id, 'file_downloaded', {
            'file_size_bytes': len(file_content),
            'object_key': object_key
        })
        
        # Parse CSV
        csv_reader = csv.DictReader(StringIO(file_content))
        valid_records = []
        invalid_records = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 for header
            validation_result = validate_smartphone_record(row, row_num)
            
            if validation_result['is_valid']:
                # Add processing metadata
                row['processed_at'] = datetime.utcnow().isoformat()
                row['correlation_id'] = correlation_id
                row['source_file'] = object_key
                valid_records.append(row)
            else:
                # Add rejection metadata
                invalid_record = {
                    **row,
                    'rejection_reasons': ', '.join(validation_result['errors']),
                    'rejected_at': datetime.utcnow().isoformat(),
                    'correlation_id': correlation_id,
                    'row_number': row_num,
                    'source_file': object_key
                }
                invalid_records.append(invalid_record)
        
        log_event(correlation_id, 'csv_parsed', {
            'total_rows': len(valid_records) + len(invalid_records),
            'valid_rows': len(valid_records),
            'invalid_rows': len(invalid_records)
        })
        
        return valid_records, invalid_records
        
    except Exception as e:
        log_event(correlation_id, 'file_processing_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'object_key': object_key
        }, level='ERROR')
        raise

def validate_smartphone_record(record: Dict, row_num: int) -> Dict:

    errors = []
    
    # Required fields validation
    required_fields = ['order_id', 'date', 'brand', 'price', 'region']
    for field in required_fields:
        if not record.get(field) or str(record[field]).strip() == '':
            errors.append(f"Missing required field: {field}")
    
    # Price validation
    try:
        price = float(record.get('price', 0))
        if price <= 0:
            errors.append("Price must be greater than 0")
        if price > 10000:  # Reasonable upper limit
            errors.append("Price exceeds maximum limit (10000)")
    except (ValueError, TypeError):
        errors.append("Invalid price format - must be a number")
    
    # RAM validation
    try:
        ram = str(record.get('ram', '')).strip()
        if ram and ram not in ['N/A', '']:
            ram_value = int(ram)
            if ram_value <= 0:
                errors.append("RAM must be greater than 0")
            if ram_value > 32:  # Reasonable upper limit
                errors.append("RAM exceeds maximum limit (32GB)")
    except (ValueError, TypeError):
        if ram and ram not in ['N/A', '']:
            errors.append("Invalid RAM format - must be a number")
    
    # Storage validation
    try:
        storage = str(record.get('storage', '')).strip()
        if storage and storage not in ['N/A', '']:
            storage_value = int(storage)
            if storage_value <= 0:
                errors.append("Storage must be greater than 0")
    except (ValueError, TypeError):
        if storage and storage not in ['N/A', '']:
            errors.append("Invalid storage format - must be a number")
    
    # Date validation
    try:
        date_str = str(record.get('date', '')).strip()
        if date_str:
            datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        errors.append("Invalid date format - must be YYYY-MM-DD")
    
    # Region validation
    valid_regions = ['North America', 'South America', 'Europe', 'Asia', 'Africa', 'Oceania']
    region = str(record.get('region', '')).strip()
    if region and region not in valid_regions:
        errors.append(f"Invalid region - must be one of: {', '.join(valid_regions)}")
    
    # Model validation (should not be empty if brand is provided)
    model = str(record.get('model', '')).strip()
    brand = str(record.get('brand', '')).strip()
    if brand and not model:
        errors.append("Model is required when brand is provided")
    
    return {
        'is_valid': len(errors) == 0,
        'errors': errors
    }

def upload_results_with_retry(bucket_name: str, original_key: str, valid_records: List[Dict], 
                            invalid_records: List[Dict], correlation_id: str, source_etag: str,
                            max_retries: int = 3) -> Dict:

    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return upload_results(bucket_name, original_key, valid_records, 
                                invalid_records, correlation_id, source_etag)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + 1
                log_event(correlation_id, 'retrying_upload', {
                    'attempt': attempt + 1,
                    'max_retries': max_retries,
                    'wait_time': wait_time,
                    'error': str(e)
                }, level='WARNING')
                time.sleep(wait_time)
            else:
                raise
    
    raise last_exception

def upload_results(bucket_name: str, original_key: str, valid_records: List[Dict], 
                  invalid_records: List[Dict], correlation_id: str, source_etag: str) -> Dict:

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    base_filename = original_key.split('/')[-1].replace('.csv', '')
    result_files = {}
    
    # Upload valid records to processed/ folder
    if valid_records:
        processed_key = f"processed/{base_filename}_processed_{timestamp}.csv"
        upload_csv_to_s3(bucket_name, processed_key, valid_records, correlation_id, source_etag)
        result_files['processed_file'] = processed_key
        
        log_event(correlation_id, 'processed_file_created', {
            'file_key': processed_key,
            'record_count': len(valid_records)
        })
    
    # Upload invalid records to rejected/ folder
    if invalid_records:
        rejected_key = f"rejected/{base_filename}_rejected_{timestamp}.csv"
        upload_csv_to_s3(bucket_name, rejected_key, invalid_records, correlation_id, source_etag)
        result_files['rejected_file'] = rejected_key
        
        log_event(correlation_id, 'rejected_file_created', {
            'file_key': rejected_key,
            'record_count': len(invalid_records)
        })
    
    return result_files

def upload_csv_to_s3(bucket_name: str, key: str, records: List[Dict], 
                    correlation_id: str, source_etag: str):

    try:
        if not records:
            return
        
        # Convert records to CSV
        output = StringIO()
        fieldnames = records[0].keys()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        
        csv_content = output.getvalue()
        
        # Upload to S3 with metadata for idempotency tracking
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=csv_content,
            ContentType='text/csv',
            Metadata={
                'correlation-id': correlation_id,
                'processed-at': datetime.utcnow().isoformat(),
                'record-count': str(len(records)),
                'source-etag': source_etag,  # For idempotency
                'file-hash': hashlib.md5(csv_content.encode()).hexdigest()
            }
        )
        
        log_event(correlation_id, 'file_uploaded', {
            'bucket': bucket_name,
            'key': key,
            'record_count': len(records),
            'file_size_bytes': len(csv_content)
        })
        
    except Exception as e:
        log_event(correlation_id, 'upload_error', {
            'error': str(e),
            'error_type': type(e).__name__,
            'key': key
        }, level='ERROR')
        raise