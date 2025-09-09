import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'functions'))

from functions.data_processor.data_processor import validate_smartphone_record, log_event, create_response

class TestDataProcessor(unittest.TestCase):
    
    def test_validate_valid_smartphone_record(self):
        """Test validation of a valid smartphone record"""
        valid_record = {
            'order_id': 'ORD1001',
            'date': '2024-03-26',
            'model': 'iPhone 15',
            'brand': 'Apple',
            'release_year': '2024',
            'price': '999',
            'region': 'North America',
            'customer_review': 'Great phone!',
            'ram': '8',
            'storage': '256',
            'color': 'Blue'
        }
        
        result = validate_smartphone_record(valid_record, 2)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(len(result['errors']), 0)
    
    def test_validate_invalid_smartphone_record_missing_required_fields(self):
        """Test validation of smartphone record with missing required fields"""
        invalid_record = {
            'order_id': '',  # Missing required field
            'date': '2024-03-26',
            'model': '',     # Missing model when brand is provided
            'brand': 'Apple',
            'price': '',     # Missing required field
            'region': '',    # Missing required field
            'ram': '8',
            'storage': '256'
        }
        
        result = validate_smartphone_record(invalid_record, 2)
        
        self.assertFalse(result['is_valid'])
        self.assertGreater(len(result['errors']), 0)
        
        # Check for specific error messages
        error_messages = result['errors']
        self.assertTrue(any('Missing required field: order_id' in msg for msg in error_messages))
        self.assertTrue(any('Missing required field: price' in msg for msg in error_messages))
        self.assertTrue(any('Missing required field: region' in msg for msg in error_messages))
        self.assertTrue(any('Model is required when brand is provided' in msg for msg in error_messages))
    
    def test_validate_invalid_price_formats(self):
        """Test validation of various invalid price formats"""
        base_record = {
            'order_id': 'ORD1001',
            'date': '2024-03-26',
            'model': 'iPhone 15',
            'brand': 'Apple',
            'region': 'North America',
            'ram': '8',
            'storage': '256'
        }
        
        # Test negative price
        record_negative = {**base_record, 'price': '-100'}
        result = validate_smartphone_record(record_negative, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Price must be greater than 0' in msg for msg in result['errors']))
        
        # Test zero price
        record_zero = {**base_record, 'price': '0'}
        result = validate_smartphone_record(record_zero, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Price must be greater than 0' in msg for msg in result['errors']))
        
        # Test invalid price format
        record_invalid = {**base_record, 'price': 'not_a_number'}
        result = validate_smartphone_record(record_invalid, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Invalid price format' in msg for msg in result['errors']))
        
        # Test price exceeding maximum
        record_too_high = {**base_record, 'price': '15000'}
        result = validate_smartphone_record(record_too_high, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Price exceeds maximum limit' in msg for msg in result['errors']))
    
    def test_validate_invalid_ram_storage(self):
        """Test validation of invalid RAM and storage values"""
        base_record = {
            'order_id': 'ORD1001',
            'date': '2024-03-26',
            'model': 'iPhone 15',
            'brand': 'Apple',
            'price': '999',
            'region': 'North America'
        }
        
        # Test negative RAM
        record_negative_ram = {**base_record, 'ram': '-8', 'storage': '256'}
        result = validate_smartphone_record(record_negative_ram, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('RAM must be greater than 0' in msg for msg in result['errors']))
        
        # Test invalid RAM format
        record_invalid_ram = {**base_record, 'ram': 'invalid', 'storage': '256'}
        result = validate_smartphone_record(record_invalid_ram, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Invalid RAM format' in msg for msg in result['errors']))
        
        # Test negative storage
        record_negative_storage = {**base_record, 'ram': '8', 'storage': '-128'}
        result = validate_smartphone_record(record_negative_storage, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Storage must be greater than 0' in msg for msg in result['errors']))
        
        # Test N/A values (should be valid)
        record_na_values = {**base_record, 'ram': 'N/A', 'storage': 'N/A'}
        result = validate_smartphone_record(record_na_values, 2)
        self.assertTrue(result['is_valid'])
    
    def test_validate_invalid_date_region(self):
        """Test validation of invalid date and region values"""
        base_record = {
            'order_id': 'ORD1001',
            'model': 'iPhone 15',
            'brand': 'Apple',
            'price': '999',
            'ram': '8',
            'storage': '256'
        }
        
        # Test invalid date format
        record_invalid_date = {**base_record, 'date': '26-03-2024', 'region': 'North America'}
        result = validate_smartphone_record(record_invalid_date, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Invalid date format' in msg for msg in result['errors']))
        
        # Test invalid region
        record_invalid_region = {**base_record, 'date': '2024-03-26', 'region': 'Invalid Region'}
        result = validate_smartphone_record(record_invalid_region, 2)
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Invalid region' in msg for msg in result['errors']))
    
    @patch('data_processor.logger')
    def test_log_event_info(self, mock_logger):
        """Test structured logging for info level"""
        correlation_id = 'test-123'
        event_type = 'test_event'
        details = {'key': 'value', 'number': 42}
        
        log_event(correlation_id, event_type, details)
        
        # Verify logger.info was called once
        mock_logger.info.assert_called_once()
        
        # Get the logged message and parse it
        logged_message = mock_logger.info.call_args[0][0]
        import json
        parsed_log = json.loads(logged_message)
        
        # Verify log structure
        self.assertEqual(parsed_log['correlation_id'], correlation_id)
        self.assertEqual(parsed_log['event'], event_type)
        self.assertEqual(parsed_log['key'], 'value')
        self.assertEqual(parsed_log['number'], 42)
        self.assertIn('timestamp', parsed_log)
    
    @patch('data_processor.logger')
    def test_log_event_error(self, mock_logger):
        """Test structured logging for error level"""
        correlation_id = 'test-456'
        event_type = 'error_event'
        details = {'error': 'Something went wrong'}
        
        log_event(correlation_id, event_type, details, level='ERROR')
        
        # Verify logger.error was called
        mock_logger.error.assert_called_once()
        
        # Get the logged message and parse it
        logged_message = mock_logger.error.call_args[0][0]
        import json
        parsed_log = json.loads(logged_message)
        
        # Verify log structure
        self.assertEqual(parsed_log['correlation_id'], correlation_id)
        self.assertEqual(parsed_log['event'], event_type)
        self.assertEqual(parsed_log['error'], 'Something went wrong')
    
    def test_create_response(self):
        """Test Lambda response creation"""
        body = {'message': 'Success', 'data': {'count': 5}}
        response = create_response(200, body)
        
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(response['headers']['Content-Type'], 'application/json')
        
        import json
        parsed_body = json.loads(response['body'])
        self.assertEqual(parsed_body['message'], 'Success')
        self.assertEqual(parsed_body['data']['count'], 5)
    
    def test_edge_cases(self):
        """Test edge cases in validation"""
        # Test empty record
        empty_record = {}
        result = validate_smartphone_record(empty_record, 1)
        self.assertFalse(result['is_valid'])
        self.assertGreater(len(result['errors']), 0)
        
        # Test record with None values
        none_record = {
            'order_id': None,
            'date': None,
            'brand': None,
            'price': None,
            'region': None
        }
        result = validate_smartphone_record(none_record, 1)
        self.assertFalse(result['is_valid'])
        
        # Test record with whitespace-only values
        whitespace_record = {
            'order_id': '   ',
            'date': '\t',
            'brand': '\n',
            'price': '  ',
            'region': '   '
        }
        result = validate_smartphone_record(whitespace_record, 1)
        self.assertFalse(result['is_valid'])

if __name__ == '__main__':
    unittest.main()