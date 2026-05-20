import base64
from io import BytesIO
from app.core.graph_mailer import send_graph_email


def send_rgt_invite(to_emails: list, cc_emails: list, touchpoint_data: dict, rgt_buffer: BytesIO) -> bool:
    """
    Sends the RGT to collect technical specs from the bank team.

    TO: Owner + Technical Owner + Module Owner
    CC: Department email
    Attachment: RGT Word document
    """
    wud_id = touchpoint_data.get('id', 'TBD')
    api_name = touchpoint_data.get('name', 'Unnamed Integration')
    source = touchpoint_data.get('source', '')
    module = touchpoint_data.get('module', '')

    if not to_emails:
        print(f"[RGT] No recipients for WUD-ID:{wud_id}. Skipping.")
        return False

    subject = f"ACTION REQUIRED: Technical Specifications for {api_name} [WUD-ID:{wud_id}]"

    html_body = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 30px 10px; margin: 0;">
        <div style="max-width: 620px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-top: 4px solid #4338ca;">
            <div style="background: #1a233a; padding: 18px; text-align: center;">
                <h2 style="color: white; margin: 0; font-size: 18px;">SDG<span style="color: #8b5cf6;">NEXT</span></h2>
                <p style="color: #94a3b8; font-size: 10px; margin-top: 4px; text-transform: uppercase; letter-spacing: 1px;">Requirement Gathering Template</p>
            </div>
            <div style="padding: 30px 35px;">
                <h2 style="margin: 0 0 5px 0; color: #0f172a; font-size: 18px;">{api_name}</h2>
                <p style="color: #64748b; font-size: 12px; margin: 0 0 20px 0;">{module} &middot; {source} &middot; WUD-ID: {wud_id}</p>

                <div style="color: #334155; font-size: 14px; line-height: 1.6; margin-bottom: 20px;">
                    Hello Team,<br><br>
                    We are initiating the integration process for <strong>{api_name}</strong>.
                    Attached is the <strong>Requirement Gathering Template (RGT)</strong> with pre-filled functional requirements.
                </div>

                <div style="background: #fef3c7; border: 1px solid #fde68a; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px;">
                    <div style="font-size: 11px; font-weight: 700; color: #92400e; text-transform: uppercase; margin-bottom: 8px;">Action Required</div>
                    <ol style="font-size: 13px; color: #78350f; margin: 0; padding-left: 18px; line-height: 1.8;">
                        <li>Open the attached Word document</li>
                        <li>Fill in technical details in the white cells (URLs, Payloads, Auth)</li>
                        <li>Save the document</li>
                        <li><strong>Reply to this email</strong> with the updated document attached</li>
                    </ol>
                </div>

                <p style="font-size: 12px; color: #94a3b8; margin: 15px 0 0 0; border-top: 1px solid #e2e8f0; padding-top: 12px;">
                    Do not alter the table structure or change the email subject line - responses are processed automatically.
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    # Build attachment for Graph API
    safe_name = api_name.replace(" ", "_").replace("/", "-")
    file_bytes = rgt_buffer.read()
    file_b64 = base64.b64encode(file_bytes).decode("utf-8")

    attachments = [{
        "name": f"RGT_{safe_name}_Spec.docx",
        "contentType": (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        "contentBytes": file_b64,
    }]

    result = send_graph_email(
        to_recipients=to_emails,
        subject=subject,
        html_body=html_body,
        cc_recipients=cc_emails if cc_emails else None,
        attachments=attachments
    )

    if result["success"]:
        print(f"[RGT] Sent WUD-ID:{wud_id} | TO: {', '.join(to_emails)} | CC: {', '.join(cc_emails)}")
        return True
    else:
        print(f"[RGT] FAILED WUD-ID:{wud_id}: {result['error']}")
        return False