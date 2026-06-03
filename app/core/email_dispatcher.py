import base64
from io import BytesIO
from app.core.graph_mailer import send_graph_email, find_latest_in_conversation, reply_to_sent_message


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


def send_rgt_missing_fields_reply(wud_id: int, api_name: str,
                                   missing_fields: list,
                                   completion_pct: int,
                                   filled_count: int,
                                   total_fields: int,
                                   bank_email: str = "",
                                   bank_doc_bytes: bytes = None) -> bool:
    """
    Sends a reply on the same RGT email thread listing the missing fields.
    Attaches the bank's own document back so they can continue filling it.
    Used for 1-99% completion case.
    """
    if not missing_fields:
        return False

    original_subject = f"ACTION REQUIRED: Technical Specifications for {api_name} [WUD-ID:{wud_id}]"
    latest_msg_id = find_latest_in_conversation(original_subject)

    if not latest_msg_id:
        print(f"[RGT Gap] WUD-ID:{wud_id} — Could not find original email thread.")
        return False

    rows_html = ""
    for i, field in enumerate(missing_fields, 1):
        rows_html += (
            f'<tr style="border-bottom: 1px solid #e2e8f0;">'
            f'<td style="padding: 8px 12px; font-size: 13px; color: #64748b;">{i}</td>'
            f'<td style="padding: 8px 12px; font-size: 13px; color: #1e293b; font-weight: 500;">{field["label"]}</td>'
            f'<td style="padding: 8px 12px; text-align: center;">'
            f'<span style="background: #fef2f2; color: #dc2626; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px;">MISSING</span>'
            f'</td>'
            f'</tr>'
        )

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; max-width: 620px;">
        <div style="background: #fef3c7; border: 1px solid #fde68a; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #92400e; text-transform: uppercase; margin-bottom: 6px;">Incomplete Response — Action Required</div>
            <p style="font-size: 13px; color: #78350f; margin: 0; line-height: 1.6;">
                Thank you for your response on <strong>{api_name}</strong>.
                However, <strong>{len(missing_fields)} of {total_fields}</strong> required fields are still missing.
                Current completion: <strong>{completion_pct}%</strong>.
            </p>
        </div>

        <p style="font-size: 13px; color: #334155; margin-bottom: 16px;">
            Please fill the missing fields listed below in the attached document and reply again:
        </p>

        <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
            <thead>
                <tr style="background: #1a233a;">
                    <th style="padding: 10px 12px; font-size: 11px; color: white; text-align: left; width: 40px;">#</th>
                    <th style="padding: 10px 12px; font-size: 11px; color: white; text-align: left;">Required Field</th>
                    <th style="padding: 10px 12px; font-size: 11px; color: white; text-align: center; width: 80px;">Status</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <div style="margin-top: 20px; padding: 14px 18px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px;">
            <p style="font-size: 12px; color: #166534; margin: 0; line-height: 1.6;">
                <strong>Completed:</strong> {filled_count}/{total_fields} ({completion_pct}%)<br>
                <strong>Remaining:</strong> {len(missing_fields)} fields<br><br>
                Your partially filled document is attached. Please complete it and <strong>reply to this email</strong>.
            </p>
        </div>
    </div>
    """

    # Attach the bank's document back
    attachments = None
    if bank_doc_bytes:
        file_b64 = base64.b64encode(bank_doc_bytes).decode("utf-8")
        safe_name = api_name.replace(" ", "_").replace("/", "-")
        attachments = [{
            "name": f"RGT_{safe_name}_Partial.docx",
            "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "contentBytes": file_b64,
        }]

    to_list = [bank_email] if bank_email else None
    result = reply_to_sent_message(latest_msg_id, html_body,
                                   to_recipients=to_list,
                                   attachments=attachments)

    if result["success"]:
        print(f"[RGT Gap] WUD-ID:{wud_id} — Sent missing fields reply ({len(missing_fields)} missing)")
        return True
    else:
        print(f"[RGT Gap] WUD-ID:{wud_id} — Reply failed: {result['error']}")
        return False


def send_rgt_not_filled_reply(wud_id: int, api_name: str,
                              bank_email: str = "",
                              rgt_buffer: BytesIO = None) -> bool:
    """
    Used when bank returns a 0% filled document.
    Re-sends the regenerated RGT with a message asking them to fill it.
    """
    original_subject = f"ACTION REQUIRED: Technical Specifications for {api_name} [WUD-ID:{wud_id}]"
    latest_msg_id = find_latest_in_conversation(original_subject)

    if not latest_msg_id:
        print(f"[RGT 0%] WUD-ID:{wud_id} — Could not find original email thread.")
        return False

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; max-width: 620px;">
        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #991b1b; text-transform: uppercase; margin-bottom: 6px;">Document Not Filled</div>
            <p style="font-size: 13px; color: #7f1d1d; margin: 0; line-height: 1.6;">
                The document received for <strong>{api_name}</strong> appears to be unfilled.
                None of the required technical specifications were provided.
            </p>
        </div>

        <p style="font-size: 13px; color: #334155; margin-bottom: 16px; line-height: 1.6;">
            Please open the attached Requirement Gathering Template, fill in the required
            technical details (URLs, payloads, authentication, etc.), save the document,
            and <strong>reply to this email</strong> with the completed file attached.
        </p>

        <p style="font-size: 11px; color: #94a3b8; margin-top: 16px;">
            This is an automated message from SDGNext. Do not alter the email subject line.
        </p>
    </div>
    """

    # Attach the regenerated RGT
    attachments = None
    if rgt_buffer:
        file_bytes = rgt_buffer.read()
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        safe_name = api_name.replace(" ", "_").replace("/", "-")
        attachments = [{
            "name": f"RGT_{safe_name}_Spec.docx",
            "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "contentBytes": file_b64,
        }]

    to_list = [bank_email] if bank_email else None
    result = reply_to_sent_message(latest_msg_id, html_body,
                                   to_recipients=to_list,
                                   attachments=attachments)

    if result["success"]:
        print(f"[RGT 0%] WUD-ID:{wud_id} — Sent 'not filled' reply with fresh RGT")
        return True
    else:
        print(f"[RGT 0%] WUD-ID:{wud_id} — Reply failed: {result['error']}")
        return False


def send_rgt_wrong_doc_reply(wud_id: int, api_name: str,
                             bank_email: str = "",
                             rgt_buffer: BytesIO = None) -> bool:
    """
    Used when bank sends a document that doesn't match our RGT structure.
    Re-sends the regenerated RGT with a message about wrong document.
    """
    original_subject = f"ACTION REQUIRED: Technical Specifications for {api_name} [WUD-ID:{wud_id}]"
    latest_msg_id = find_latest_in_conversation(original_subject)

    if not latest_msg_id:
        print(f"[RGT Wrong] WUD-ID:{wud_id} — Could not find original email thread.")
        return False

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; max-width: 620px;">
        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px;">
            <div style="font-size: 11px; font-weight: 700; color: #991b1b; text-transform: uppercase; margin-bottom: 6px;">Wrong Document Received</div>
            <p style="font-size: 13px; color: #7f1d1d; margin: 0; line-height: 1.6;">
                The document received for <strong>{api_name}</strong> does not match the
                Requirement Gathering Template (RGT) format we shared earlier.
            </p>
        </div>

        <p style="font-size: 13px; color: #334155; margin-bottom: 16px; line-height: 1.6;">
            Please use the attached RGT template to provide technical specifications.
            Fill in the required fields in the white cells, save the document, and
            <strong>reply to this email</strong> with the correct file attached.
        </p>

        <p style="font-size: 11px; color: #94a3b8; margin-top: 16px;">
            This is an automated message from SDGNext. Do not alter the table structure or email subject line.
        </p>
    </div>
    """

    # Attach the regenerated RGT
    attachments = None
    if rgt_buffer:
        file_bytes = rgt_buffer.read()
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        safe_name = api_name.replace(" ", "_").replace("/", "-")
        attachments = [{
            "name": f"RGT_{safe_name}_Spec.docx",
            "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "contentBytes": file_b64,
        }]

    to_list = [bank_email] if bank_email else None
    result = reply_to_sent_message(latest_msg_id, html_body,
                                   to_recipients=to_list,
                                   attachments=attachments)

    if result["success"]:
        print(f"[RGT Wrong] WUD-ID:{wud_id} — Sent 'wrong document' reply with fresh RGT")
        return True
    else:
        print(f"[RGT Wrong] WUD-ID:{wud_id} — Reply failed: {result['error']}")
        return False