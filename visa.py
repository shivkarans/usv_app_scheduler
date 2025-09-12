import time
import json
import requests
import configparser
import random
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from embassy import *

config = configparser.ConfigParser()
config.read('config.ini')

# Personal Info:
# Account and current appointment info from https://ais.usvisa-info.com
USERNAME = config['PERSONAL_INFO']['USERNAME']
PASSWORD = config['PERSONAL_INFO']['PASSWORD']
# Find SCHEDULE_ID in re-schedule page link:
# https://ais.usvisa-info.com/en-am/niv/schedule/{SCHEDULE_ID}/appointment
SCHEDULE_ID = config['PERSONAL_INFO']['SCHEDULE_ID']
# Target Period:
PRIOD_START = config['PERSONAL_INFO']['PRIOD_START']
PRIOD_END = config['PERSONAL_INFO']['PRIOD_END']
# Embassy Section:
YOUR_EMBASSY = config['PERSONAL_INFO']['YOUR_EMBASSY'] 
EMBASSY = Embassies[YOUR_EMBASSY][0]
FACILITY_ID = Embassies[YOUR_EMBASSY][1]
REGEX_CONTINUE = Embassies[YOUR_EMBASSY][2]

# Notification:
# Get email notifications via https://sendgrid.com/ (Optional)
SENDGRID_API_KEY = config['NOTIFICATION']['SENDGRID_API_KEY']
SENDGRID_EMAIL_SENDER = config['NOTIFICATION']['SENDGRID_EMAIL_SENDER']

# Get push notifications via PERSONAL WEBSITE http://yoursite.com (Optional)

# Time Section:
minute = 60
hour = 60 * minute
# Time between steps (interactions with forms)
STEP_TIME = 0.5
# Time between retries/checks for available dates (seconds)
RETRY_TIME = config['TIME'].getfloat('RETRY_TIME')
# Cooling down after WORK_LIMIT_TIME hours of work (Avoiding Ban)
WORK_LIMIT_TIME = config['TIME'].getfloat('WORK_LIMIT_TIME')
WORK_COOLDOWN_TIME = config['TIME'].getfloat('WORK_COOLDOWN_TIME')
# Temporary Banned (empty list): wait COOLDOWN_TIME hours
BAN_COOLDOWN_TIME = config['TIME'].getfloat('BAN_COOLDOWN_TIME')

# CHROMEDRIVER
# Details for the script to control Chrome
LOCAL_USE = config['CHROMEDRIVER'].getboolean('LOCAL_USE')
# Optional: HUB_ADDRESS is mandatory only when LOCAL_USE = False
HUB_ADDRESS = config['CHROMEDRIVER']['HUB_ADDRESS']

SIGN_IN_LINK = f"https://ais.usvisa-info.com/{EMBASSY}/niv/users/sign_in"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment"
DATE_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
SIGN_OUT_LINK = f"https://ais.usvisa-info.com/{EMBASSY}/niv/users/sign_out"

JS_SCRIPT = ("var req = new XMLHttpRequest();"
             f"req.open('GET', '%s', false);"
             "req.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');"
             "req.setRequestHeader('X-Requested-With', 'XMLHttpRequest');"
             f"req.setRequestHeader('Cookie', '_yatri_session=%s');"
             "req.send(null);"
             "return req.responseText;")

# Driver will be initialized when portal is open
driver = None

def send_notification(title, msg):
    print(f"📧 NOTIFICATION: {title}")
    print(f"📝 Message: {msg}")
    # TODO: Configure SendGrid later if needed
    pass



def auto_action(label, find_by, el_type, action, value, sleep_time=0):
    print("\t"+ label +":", end="")
    # Find Element By
    match find_by.lower():
        case 'id':
            item = driver.find_element(By.ID, el_type)
        case 'name':
            item = driver.find_element(By.NAME, el_type)
        case 'class':
            item = driver.find_element(By.CLASS_NAME, el_type)
        case 'xpath':
            item = driver.find_element(By.XPATH, el_type)
        case _:
            return 0
    # Do Action:
    match action.lower():
        case 'send':
            item.send_keys(value)
        case 'click':
            item.click()
        case _:
            return 0
    print("\t\tCheck!")
    if sleep_time:
        time.sleep(sleep_time)


def start_process():
    # Bypass reCAPTCHA
    driver.get(SIGN_IN_LINK)
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))
    auto_action("Click bounce", "xpath", '//a[@class="down-arrow bounce"]', "click", "", STEP_TIME)
    auto_action("Email", "id", "user_email", "send", USERNAME, STEP_TIME)
    auto_action("Password", "id", "user_password", "send", PASSWORD, STEP_TIME)
    auto_action("Privacy", "class", "icheckbox", "click", "", STEP_TIME)
    auto_action("Enter Panel", "name", "commit", "click", "", STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '" + REGEX_CONTINUE + "')]")))
    print("\n\tlogin successful!\n")

def reschedule(date):
    appointment_time = get_time(date)
    driver.get(APPOINTMENT_URL)
    
    # Wait for page to load
    Wait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "form")))
    
    try:
        # Try to use Selenium to fill and submit the form directly
        print(f"Attempting to reschedule to {date} {appointment_time} using Selenium form submission...")
        
        # Find and fill the date field
        date_field = driver.find_element(By.ID, "appointments_consulate_appointment_date")
        driver.execute_script("arguments[0].value = arguments[1];", date_field, date)
        print(f"Set date field to: {date}")
        
        # Trigger change event on date field to populate time options
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", date_field)
        time.sleep(3)  # Wait for time options to load
        
        # Find and select the time
        time_field = driver.find_element(By.ID, "appointments_consulate_appointment_time")
        
        # Debug: Print available time options
        from selenium.webdriver.support.ui import Select
        select = Select(time_field)
        available_times = [option.get_attribute('value') for option in select.options if option.get_attribute('value')]
        print(f"Available times: {available_times}")
        print(f"Looking for time: {appointment_time}")
        
        # Try to select the exact time, or the first available time
        if appointment_time in available_times:
            select.select_by_value(appointment_time)
            print(f"Selected exact time: {appointment_time}")
        elif available_times:
            # Select the first available time
            first_time = available_times[0]
            select.select_by_value(first_time)
            print(f"Selected first available time: {first_time}")
            appointment_time = first_time  # Update the appointment_time variable
        else:
            raise Exception("No time slots available for selected date")
        
        # Find and click the submit button
        submit_button = driver.find_element(By.NAME, "commit")
        submit_button.click()
        print("Clicked submit button")
        
        # Wait for response and check result
        time.sleep(3)
        page_source = driver.page_source
        
        # Check for various success indicators
        success_indicators = [
            "Successfully Scheduled",
            "successfully scheduled", 
            "appointment has been scheduled",
            "Appointment Scheduled",
            "confirmation",
            "confirmed"
        ]
        
        # Also check the current URL for success indicators
        current_url = driver.current_url
        
        is_success = any(indicator in page_source.lower() for indicator in [s.lower() for s in success_indicators])
        
        if is_success or "confirmation" in current_url.lower():
            title = "SUCCESS"
            msg = f"Rescheduled Successfully! {date} {appointment_time}"
            print("✅ SUCCESS: Appointment rescheduled!")
            print(f"Current URL: {current_url}")
            print(f"Page title: {driver.title}")
        else:
            title = "FAIL"
            msg = f"Reschedule Failed!!! {date} {appointment_time}"
            print("❌ FAIL: Could not reschedule appointment")
            print(f"Page title: {driver.title}")
            print(f"Current URL: {current_url}")
            # Save page source for debugging
            with open("debug_page.html", "w") as f:
                f.write(page_source)
            print("Saved page source to debug_page.html for inspection")
            # Print first 1000 chars of response for debugging
            print(f"Page content preview: {page_source[:1000]}")
        
        return [title, msg]
        
    except Exception as e:
        print(f"Exception in Selenium form submission: {e}")
        
        # Fallback to HTTP request method
        print("Falling back to HTTP request method...")
        headers = {
            "User-Agent": driver.execute_script("return navigator.userAgent;"),
            "Referer": APPOINTMENT_URL,
            "Cookie": "_yatri_session=" + driver.get_cookie("_yatri_session")["value"]
        }
        
        data = {
            "appointments[consulate_appointment][facility_id]": FACILITY_ID,
            "appointments[consulate_appointment][date]": date,
            "appointments[consulate_appointment][time]": appointment_time,
        }
        
        # Try to get authenticity token
        try:
            auth_token_element = driver.find_element(by=By.NAME, value='authenticity_token')
            data["authenticity_token"] = auth_token_element.get_attribute('value')
        except:
            pass
        
        r = requests.post(APPOINTMENT_URL, headers=headers, data=data)
        
        if r.text.find('Successfully Scheduled') != -1:
            title = "SUCCESS"
            msg = f"Rescheduled Successfully! {date} {appointment_time}"
        else:
            title = "FAIL"
            msg = f"Reschedule Failed!!! {date} {appointment_time}"
        return [title, msg]


def get_date():
    # Requesting to get the whole available dates
    session = driver.get_cookie("_yatri_session")["value"]
    script = JS_SCRIPT % (str(DATE_URL), session)
    content = driver.execute_script(script)
    return json.loads(content)

def get_time(date):
    time_url = TIME_URL % date
    session = driver.get_cookie("_yatri_session")["value"]
    script = JS_SCRIPT % (str(time_url), session)
    content = driver.execute_script(script)
    data = json.loads(content)
    time = data.get("available_times")[-1]
    print(f"Got time successfully! {date} {time}")
    return time


def is_logged_in():
    content = driver.page_source
    if(content.find("error") != -1):
        return False
    return True


def get_available_date(dates):
    # Evaluation of different available dates
    def is_in_period(date, PSD, PED):
        new_date = datetime.strptime(date, "%Y-%m-%d")
        result = ( PED > new_date and new_date > PSD )
        # print(f'{new_date.date()} : {result}', end=", ")
        return result
    
    PED = datetime.strptime(PRIOD_END, "%Y-%m-%d")
    PSD = datetime.strptime(PRIOD_START, "%Y-%m-%d")
    for d in dates:
        date = d.get('date')
        if is_in_period(date, PSD, PED):
            return date
    print(f"\n\nNo available dates between ({PSD.date()}) and ({PED.date()})!")


def info_logger(file_path, log):
    # file_path: e.g. "log.txt"
    with open(file_path, "a") as file:
        file.write(str(datetime.now().time()) + ":\n" + log + "\n")


def is_portal_open():
    """Check if visa portal is likely open (7 PM to 6 AM next day)"""
    current_time = datetime.now().time()
    # Portal opens at 7 PM (19:00) and closes around 6 AM (06:00) next day
    portal_open_time = datetime.strptime("19:00", "%H:%M").time()
    portal_close_time = datetime.strptime("06:00", "%H:%M").time()
    
    # If current time is between 7 PM and midnight, or between midnight and 6 AM
    if current_time >= portal_open_time or current_time <= portal_close_time:
        return True
    return False

def time_until_portal_opens():
    """Calculate time until portal opens at 7 PM"""
    now = datetime.now()
    today_7pm = now.replace(hour=19, minute=0, second=0, microsecond=0)
    
    # If it's already past 7 PM today, portal opens tomorrow at 7 PM
    if now.time() > datetime.strptime("19:00", "%H:%M").time():
        tomorrow_7pm = today_7pm + timedelta(days=1)
        time_diff = tomorrow_7pm - now
    else:
        time_diff = today_7pm - now
    
    hours = int(time_diff.total_seconds() // 3600)
    minutes = int((time_diff.total_seconds() % 3600) // 60)
    return hours, minutes

def initialize_driver():
    """Initialize the browser driver"""
    global driver
    
    # Clean up any existing driver first
    if driver is not None:
        try:
            driver.quit()
        except:
            pass
        driver = None
    
    # Kill any hanging chromedriver processes
    import subprocess
    try:
        subprocess.run(['pkill', '-f', 'chromedriver'], check=False)
        time.sleep(2)  # Wait for processes to clean up
    except:
        pass
    
    # Initialize new driver
    try:
        if LOCAL_USE:
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
        else:
            driver = webdriver.Remote(command_executor=HUB_ADDRESS, options=webdriver.ChromeOptions())
        print("✅ Browser initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize browser: {e}")
        # Try alternative approach
        try:
            print("🔄 Trying alternative ChromeDriver initialization...")
            service = ChromeService()
            driver = webdriver.Chrome(service=service)
            print("✅ Alternative browser initialization successful")
        except Exception as e2:
            print(f"❌ Alternative initialization also failed: {e2}")
            raise Exception(f"Could not initialize browser after multiple attempts: {e}, {e2}")

if __name__ == "__main__":
    first_loop = True
    msg = ""
    END_MSG_TITLE = "COMPLETED"
    
    print("🚀 US Visa Appointment Rescheduler Started!")
    print("=" * 50)
    
    while 1:
        LOG_FILE_NAME = "log_" + str(datetime.now().date()) + ".txt"
        
        # Check if portal is open before proceeding
        if not is_portal_open():
            hours, minutes = time_until_portal_opens()
            current_time = datetime.now().strftime("%H:%M")
            total_minutes_until_open = hours * 60 + minutes
            
            # Smart sleep logic
            if total_minutes_until_open <= 5:
                # Less than 5 minutes - wait exactly until portal opens + 1 minute buffer
                wait_time = (total_minutes_until_open + 1) * 60
                print(f"⏰ Portal opens in {total_minutes_until_open} minutes! Waiting {total_minutes_until_open + 1} minutes...")
            elif total_minutes_until_open <= 30:
                # 5-30 minutes - wait exactly until portal opens
                wait_time = total_minutes_until_open * 60
                print(f"⏰ Portal opens in {total_minutes_until_open} minutes! Waiting exactly until portal opens...")
            else:
                # More than 30 minutes - wait 30 minutes and check again
                wait_time = 30 * 60
                print(f"⏰ Portal closed (Current time: {current_time}). Portal opens at 7:00 PM.")
                print(f"⏳ {hours}h {minutes}m until portal opens. Sleeping 30 minutes before checking again...")
            
            msg = f"Portal closed at {current_time}. Waiting {hours}h {minutes}m until 7:00 PM opening."
            info_logger(LOG_FILE_NAME, msg)
            
            time.sleep(wait_time)
            continue
        
        if first_loop:
            t0 = time.time()
            total_time = 0
            Req_count = 0
            print("🔓 Portal is open! Initializing browser...")
            
            # Initialize browser only when portal is open
            initialize_driver()
            
            print("🔓 Browser ready! Starting login process...")
            start_process()
            first_loop = False
        Req_count += 1
        try:
            msg = "-" * 60 + f"\nRequest count: {Req_count}, Log time: {datetime.today()}\n"
            print(msg)
            info_logger(LOG_FILE_NAME, msg)
            dates = get_date()
            if not dates:
                current_time = datetime.now().strftime("%H:%M")
                
                if is_portal_open():
                    # Portal should be open but list is empty - likely banned
                    msg = f"🚫 List is empty during portal hours ({current_time}). Likely banned or rate limited!\n⏳ Sleeping for {BAN_COOLDOWN_TIME} hours before retrying...\n"
                    notification_title = "RATE LIMITED / BANNED"
                else:
                    # Portal might be closing or having issues
                    msg = f"📭 List is empty ({current_time}). Portal may be closing or having issues.\n⏳ Sleeping for {BAN_COOLDOWN_TIME} hours before retrying...\n"
                    notification_title = "PORTAL ISSUES"
                
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                send_notification(notification_title, msg)
                driver.get(SIGN_OUT_LINK)
                time.sleep(BAN_COOLDOWN_TIME * hour)
                first_loop = True
            else:
                # Print Available dates:
                msg = ""
                for d in dates:
                    msg = msg + "%s" % (d.get('date')) + ", "
                msg = "Available dates:\n"+ msg
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                date = get_available_date(dates)
                if date:
                    # A good date to schedule for
                    send_notification("Rescheduling Started", date)
                    END_MSG_TITLE, msg = reschedule(date)
                    break
                else:
                    # Check if we're seeing unrealistic future dates (like 2027+)
                    if dates:
                        first_available = dates[0].get('date')
                        first_year = int(first_available.split('-')[0])
                        current_year = datetime.now().year
                        
                        if first_year > current_year + 1:
                            msg = f"⚠️  Only far-future dates available (earliest: {first_available}). Portal may be in maintenance mode or no real appointments available."
                            print(msg)
                            info_logger(LOG_FILE_NAME, msg)
                # Use random retry time between 5-35 seconds for human-like behavior
                RETRY_WAIT_TIME = random.randint(5, 35)
                t1 = time.time()
                total_time = t1 - t0
                msg = "\nWorking Time:  ~ {:.2f} minutes".format(total_time/minute)
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                if total_time > WORK_LIMIT_TIME * hour:
                    # Let program rest a little
                    send_notification("REST", f"Break-time after {WORK_LIMIT_TIME} hours | Repeated {Req_count} times")
                    driver.get(SIGN_OUT_LINK)
                    time.sleep(WORK_COOLDOWN_TIME * hour)
                    first_loop = True
                else:
                    msg = f"🎲 Random Retry Wait Time: {RETRY_WAIT_TIME} seconds (5-35s range)"
                    print(msg)
                    info_logger(LOG_FILE_NAME, msg)
                    time.sleep(RETRY_WAIT_TIME)
        except Exception as e:
            # Exception Occured
            msg = f"Break the loop after exception: {str(e)}\n"
            END_MSG_TITLE = "EXCEPTION"
            print(f"Exception details: {e}")
            import traceback
            traceback.print_exc()
            break

    print(msg)
    info_logger(LOG_FILE_NAME, msg)
    send_notification(END_MSG_TITLE, msg)
    
    # Clean up browser if it was initialized
    if driver is not None:
        try:
            driver.get(SIGN_OUT_LINK)
            driver.stop_client()
            driver.quit()
        except:
            pass  # Browser might already be closed
