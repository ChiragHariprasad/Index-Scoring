import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_SERVER = "smtp.zoho.in"
SMTP_PORT = 587

EMAIL_ADDRESS = "webadmin@iiflsamasta.com"
EMAIL_PASSWORD = "VUpDgzttBV95"

TO_EMAIL = "manojmadhavarao.malipatil@iiflsamasta.com"

subject = "Test Email from Zoho SMTP"
body = "Hello,\n\nThis email was sent using Zoho SMTP via indexscroing."

msg = MIMEMultipart()
msg["From"] = EMAIL_ADDRESS
msg["To"] = TO_EMAIL
msg["Subject"] = subject

msg.attach(MIMEText(body, "plain"))

try:
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()  # secure TLS
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

    server.send_message(msg)

    print("Email sent successfully")

except Exception as e:
    print("Error:", e)

finally:
    server.quit()