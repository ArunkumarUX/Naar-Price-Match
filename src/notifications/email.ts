import sgMail from "@sendgrid/mail";
import { config } from "../lib/config.js";

export async function sendAlertEmail(subject: string, body: string) {
  if (!config.SENDGRID_API_KEY) return { sent: false, reason: "no_sendgrid_key" };
  sgMail.setApiKey(config.SENDGRID_API_KEY);
  await sgMail.send({
    to: config.ALERT_EMAIL_TO,
    from: config.ALERT_EMAIL_FROM,
    subject,
    text: body,
  });
  return { sent: true };
}
