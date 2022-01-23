import boto3
import os

api_key_id = os.environ['API_KEY_ID']

def lambda_handler(event, context):
    api_gateway_client = boto3.client('apigateway')
    response = api_gateway_client.get_api_key(
        apiKey=api_key_id,
        includeValue=True
    )
    response_value = response['value']
    return {
        'PhysicalResourceId': 'APIKeyValue', 
        'IsComplete': True,
        'Data': {
            'APIKeyValue': response_value
        }
    }