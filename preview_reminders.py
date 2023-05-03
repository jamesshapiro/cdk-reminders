import boto3
import os
import argparse

ddb_client = boto3.client('dynamodb')
table_name = os.environ['REMINDERS_TABLE_NAME']



def process_items(items):
    response_items = []
    for item in items:
        reminder_body = item['reminder']['S']
        deadline = item['datetime']['S']
        print(f'{deadline}   {reminder_body}')
        response_items.append(item)
    return response_items


def get_latest_items(table_name, num_items):
    return ddb_client.query(
        TableName = table_name,
        Limit=num_items,
        ScanIndexForward=True,
        KeyConditionExpression='#pk1 = :pk1',
        ExpressionAttributeNames={
            '#pk1': 'PK1'
        },
        ExpressionAttributeValues={
            ':pk1': {'S': 'REMINDER'}
        }
    )['Items']



# make the number of items an optional command-line argument to the script
if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('-n', '--num-items', help='Num items', type=int, default=10)
    parser = args.parse_args()
    num_items = parser.num_items
    print(num_items)
    latest_items = get_latest_items(table_name, num_items)
    process_items(latest_items)