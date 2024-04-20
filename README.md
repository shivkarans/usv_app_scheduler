# visa_rescheduler

The visa_rescheduler is a bot for US VISA (usvisa-info.com) appointment rescheduling. This bot can help you reschedule your appointment to your desired time period.

## Prerequisites

- Having a US VISA appointment scheduled already.
- [Optional] API token from Sendgrid (for notifications)

## Installation

```
pip3 install -r requirements.txt
```

## Configuration

```
cp config.ini.example config.ini
```

Update configuration (username, password, target dates, ..etc)

## Running

```
python3 visa.py
```
