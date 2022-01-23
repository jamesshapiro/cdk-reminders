import json
import boto3
import os

api_key_id = os.environ['API_KEY_ID']
#api_key_arn = os.environ['API_KEY_ARN']

def lambda_handler(event, context):
    props = event['ResourceProperties']
    api_gateway_client = boto3.client('apigateway')
    print('shalom haverim!')
    print(f'{api_key_id=}')
    response = api_gateway_client.get_api_key(
        apiKey=api_key_id,
        includeValue=True
    )
    responseValue = response['value']
    responseData = {}
    print(f'{responseValue=}')
    responseData['Data'] = responseValue
    return {
        'PhysicalResourceId': 'APIKeyValue', 
        'IsComplete': True,
        'Data': {
            'APIKeyValue': responseValue
        }
    }