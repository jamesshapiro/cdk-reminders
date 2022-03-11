import hashlib
import base64
import boto3

unauthorized_error = {
    "status": '401',
    "statusDescription": 'Unauthorized',
    "body": 'Unauthorized',
    "headers": {
        'www-authenticate': [
            {"key": 'WWW-Authenticate', "value": 'Basic'}
        ]
    }
}


def lambda_handler(event, context):
    session = boto3.Session()
    iam_client = session.client("iam")
    sts_client = session.client("sts")
    ROLE_NAME = sts_client.get_caller_identity()["Arn"].split("/")[-2]
    policy_names = iam_client.list_role_policies(
        RoleName=ROLE_NAME
    )['PolicyNames']
    #print(f'{policies=}')
    POLICY_NAME = [policy_name for policy_name in policy_names if 'Default' in policy_name][0]
    #POLICY_NAME = [policy['PolicyName'] for policy in policies][0]
    ROLE_POLICY = iam_client.get_role_policy(RoleName=ROLE_NAME, PolicyName=POLICY_NAME)[
        "PolicyDocument"
    ]
    TABLE_NAME = ''
    TABLE_REGION = 'us-east-1'
    for statement in ROLE_POLICY["Statement"]:
        resource = statement["Resource"]
        if type(resource) != type([]):
            resource = [resource]
        for arn in resource:
            if arn.startswith("arn:aws:dynamodb:"):
                arn_parts = arn.split("/")
                TABLE_NAME = arn_parts[-1]
                TABLE_REGION = arn_parts[0].split(":")[3]
    ddb_client = boto3.client('dynamodb', region_name=TABLE_REGION)
    request = event['Records'][0]['cf']['request']
    headers = request['headers']
    if 'authorization' in headers:
        # auth_string == 'Basic ' + auth_token
        auth_string = headers['authorization'][0]['value']
        auth_token = auth_string[len('Basic '):]
        decoded = base64.b64decode(auth_token)
        str_decoded = decoded.decode("utf-8")
        username_and_password = str_decoded.split(':', 1)
        #make username case insensitive
        username = username_and_password[0].lower()
        password = username_and_password[1]
        response = ddb_client.get_item(
            TableName=TABLE_NAME,
            Key={
                'PK1': {
                    'S': f'USER',
                },
                'SK1': {
                    'S': f'USER#{username}',
                }
            }
        )
        if 'Item' not in response:
            return unauthorized_error
        item = response['Item']
        salt = item['SALT']['S']
        auth_hash_value = item['HASH']['S']
        m = hashlib.sha256()
        m.update(bytes(salt, 'utf-8'))
        m.update(bytes(password, 'utf-8'))
        hex_digest = str(m.hexdigest())
        if hex_digest == auth_hash_value:
            return request
        else:
            return unauthorized_error
    else:
        return unauthorized_error