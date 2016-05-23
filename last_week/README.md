# Last Week's Slack statistics

Run ./last_week.py with --help for help

This code is terrible quality.

You'll need to have API_TOKEN env variable set for a Slack API token, which you can get from https://api.slack.com/docs/oauth-test-tokens

## Uploading last week's report:

```bash
> env API_TOKEN=<YOUR_SECRET_API_TOKEN> ./last_week.py --upload
```

## Setup/Install locally

Install all required python packages:

```bash
> pip install -r requirements.txt
```
## Run in docker
Build the docker image:
``` bash
> docker build -t rands_stats .
```
Run the docker image:
``` bash
> docker run -e API_TOKEN=YOUR_SECRET_API_TOKEN -it rands_stats:latest /opt/lastweek.py --upload
```
