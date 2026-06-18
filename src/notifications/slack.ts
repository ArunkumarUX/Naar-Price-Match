import axios from "axios";
import { config } from "../lib/config.js";

export async function sendSlackAlert(text: string) {
  if (!config.SLACK_WEBHOOK_URL) return { sent: false, reason: "no_slack_webhook" };
  await axios.post(config.SLACK_WEBHOOK_URL, { text });
  return { sent: true };
}
