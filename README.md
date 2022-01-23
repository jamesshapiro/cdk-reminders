# CDK Reminders Project!

## SMS Toll-Free Number Creation Steps

1. Go to Pinpoint
1. Create a Project
1. SMS and Voice configure

- Check "Enable the SMS channel for this project"
- Select Transaction
- Set Account spending limit to something reasonable

1. Advanced configurations

- Request Phone Number
- Select Toll-free
- Select "Transactional" under Default message type

1. Go to "Test messaging"

- Enable SMS channel under "SMS" (expand steps here)
- Send yourself a message to test

```
$ cdk synth && cdk deploy
```
