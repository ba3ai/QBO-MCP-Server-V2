from __future__ import annotations

from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from app.request_context import current_user
from app.qbo import build_intuit_auth_url
from app import db
from app.service import (
    query_company,
    query_all,
    create_entity,
    get_entity,
    update_entity,
    operate_entity,
    send_transaction,
    get_report,
    search_entity,
)
from dotenv import load_dotenv

load_dotenv()

# NOTE: ChatGPT Apps / Custom Connectors require *stateless* HTTP mode for the
# HTTP/SSE transport expected by the client.
mcp = FastMCP("QBO MCP Server (OAuth + UI)", stateless_http=True, host="0.0.0.0")


def _user_id() -> str:
    u = current_user.get() or {}
    return (u.get("sub") or u.get("email") or "unknown_user").strip()


# ----------------------
# Tool documentation links (Pipedream-style)
# ----------------------

DOCS: Dict[str, str] = {
    "quickbooks-create-ap-aging-report": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/apagingdetail#query-a-report",
    "quickbooks-create-pl-report": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/profitandloss#query-a-report",
    "quickbooks-get-balance-sheet-report": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/balancesheet#query-a-report",
    "quickbooks-get-cash-flow-report": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/cashflow#query-a-report",
    "quickbooks-create-bill": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/bill#create-a-bill",
    "quickbooks-get-bill": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/bill#read-a-bill",
    "quickbooks-create-customer": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/customer#create-a-customer",
    "quickbooks-get-customer": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/most-commonly-used/customer#read-a-customer",
    "quickbooks-create-invoice": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice#create-an-invoice",
    "quickbooks-get-invoice": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice#read-an-invoice",
    "quickbooks-sparse-update-invoice": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice#sparse-update-an-invoice",
    "quickbooks-update-invoice": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice#update-an-invoice",
    "quickbooks-void-invoice": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice#void-an-invoice",
    "quickbooks-send-invoice": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice#send-an-invoice",
    "quickbooks-create-estimate": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/estimate#create-an-estimate",
    "quickbooks-update-estimate": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/estimate#update-an-estimate",
    "quickbooks-send-estimate": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/estimate#send-an-estimate",
    "quickbooks-create-payment": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/payment#create-a-payment",
    "quickbooks-get-payment": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/payment#read-a-payment",
    "quickbooks-create-purchase": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/purchase#create-a-purchase",
    "quickbooks-get-purchase": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/purchase#read-a-purchase",
    "quickbooks-delete-purchase": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/purchase#delete-a-purchase",
    "quickbooks-create-purchase-order": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/purchaseorder#create-a-purchaseorder",
    "quickbooks-get-purchase-order": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/purchaseorder#read-a-purchase-order",
    "quickbooks-create-sales-receipt": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/salesreceipt#create-a-salesreceipt",
    "quickbooks-get-sales-receipt": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/salesreceipt#read-a-salesreceipt",
    "quickbooks-get-time-activity": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/timeactivity#read-a-timeactivity-object",
    "quickbooks-search-query": "https://developer.intuit.com/app/developer/qbo/docs/develop/explore-the-quickbooks-online-api/data-queries",
    "quickbooks-search-accounts": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/account#query-an-account",
    "quickbooks-search-customers": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/customer#query-a-customer",
    "quickbooks-search-invoices": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice#query-an-invoice",
    "quickbooks-search-items": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/item#query-an-item",
    "quickbooks-search-products": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/item#query-an-item",
    "quickbooks-search-services": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/item#query-an-item",
    "quickbooks-search-purchases": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/purchase#query-a-purchase",
    "quickbooks-search-time-activities": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/timeactivity#query-a-timeactivity-object",
    "quickbooks-search-vendors": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/vendor#query-a-vendor",
    "quickbooks-update-customer": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/customer#full-update-a-customer",
    "quickbooks-update-item": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/item#full-update-an-item",
    "quickbooks-get-my-company": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/companyinfo",
    "quickbooks-create-ar-aging-report": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/aragingdetail#query-a-report",
    "quickbooks-get-ar-aging-summary-report": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/aragingdetail#query-a-report",
    "quickbooks-get-ap-aging-summary-report": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/apagingdetail#query-a-report",
}


def _desc(tool_name: str, base: str) -> str:
    """Standardize tool descriptions and append an Intuit doc link when available."""
    url = DOCS.get(tool_name)
    return f"{base} [See the documentation]({url})" if url else base


# ----------------------
# Existing helper tools
# ----------------------


@mcp.tool(
    description="Return an Intuit OAuth connect URL for the current user. Open it to connect another QBO company."
)
async def qbo_connect_company() -> Dict[str, Any]:
    uid = _user_id()
    return {"user_id": uid, "connect_url": build_intuit_auth_url(state=uid)}


@mcp.tool(description="List all connected QBO companies for the current user.")
async def qbo_list_companies() -> Dict[str, Any]:
    uid = _user_id()
    return {"user_id": uid, "companies": await db.list_connections(uid)}


@mcp.tool(description="Run a QBO Query (SQL-like) for a specific company (realm_id).")
async def qbo_query_company(realm_id: str, sql: str) -> Dict[str, Any]:
    uid = _user_id()
    return await query_company(uid, realm_id, sql)


@mcp.tool(description="Run a QBO Query (SQL-like) across all connected companies for the current user.")
async def qbo_query_all(sql: str) -> Dict[str, Any]:
    uid = _user_id()
    return await query_all(uid, sql)


# ----------------------
# Pipedream-style Tools
# ----------------------

# --- Reports ---


@mcp.tool(
    name="quickbooks-create-ap-aging-report",
    description=_desc("quickbooks-create-ap-aging-report", "Creates an AP aging report in QuickBooks Online."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_create_ap_aging_report(
    realm_id: Optional[str] = None, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Intuit report name: APAgingDetail
    return await get_report(uid, realm_id, report_name="APAgingDetail", params=params or {})


@mcp.tool(
    name="quickbooks-create-ar-aging-report",
    description=_desc("quickbooks-create-ar-aging-report", "Creates an AR aging report in QuickBooks Online."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_create_ar_aging_report(
    realm_id: Optional[str] = None, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Intuit report name: ARAgingDetail
    return await get_report(uid, realm_id, report_name="ARAgingDetail", params=params or {})


@mcp.tool(
    name="quickbooks-get-ap-aging-summary-report",
    description=_desc(
        "quickbooks-get-ap-aging-summary-report",
        "Retrieves the AP aging summary report from QuickBooks Online.",
    ),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_ap_aging_summary_report(
    realm_id: Optional[str] = None, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Intuit report name: APAgingSummary
    return await get_report(uid, realm_id, report_name="APAgingSummary", params=params or {})


@mcp.tool(
    name="quickbooks-get-ar-aging-summary-report",
    description=_desc(
        "quickbooks-get-ar-aging-summary-report",
        "Retrieves the AR aging summary report from QuickBooks Online.",
    ),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_ar_aging_summary_report(
    realm_id: Optional[str] = None, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Intuit report name: ARAgingSummary
    return await get_report(uid, realm_id, report_name="ARAgingSummary", params=params or {})


@mcp.tool(
    name="quickbooks-create-pl-report",
    description=_desc(
        "quickbooks-create-pl-report",
        "Creates a profit and loss report in QuickBooks Online.",
    ),
    annotations={"readOnlyHint": True},
)
async def quickbooks_create_pl_report(
    realm_id: Optional[str] = None, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Intuit report name: ProfitAndLoss
    return await get_report(uid, realm_id, report_name="ProfitAndLoss", params=params or {})


@mcp.tool(
    name="quickbooks-get-balance-sheet-report",
    description=_desc(
        "quickbooks-get-balance-sheet-report",
        "Retrieves the balance sheet report from QuickBooks Online.",
    ),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_balance_sheet_report(
    realm_id: Optional[str] = None, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Intuit report name: BalanceSheet
    return await get_report(uid, realm_id, report_name="BalanceSheet", params=params or {})


@mcp.tool(
    name="quickbooks-get-cash-flow-report",
    description=_desc(
        "quickbooks-get-cash-flow-report",
        "Retrieves the cash flow report from QuickBooks Online.",
    ),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_cash_flow_report(
    realm_id: Optional[str] = None, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Intuit report name: CashFlow
    return await get_report(uid, realm_id, report_name="CashFlow", params=params or {})


# --- Create ---


@mcp.tool(name="quickbooks-create-bill", description=_desc("quickbooks-create-bill", "Creates a bill."))
async def quickbooks_create_bill(
    realm_id: Optional[str] = None, bill: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="Bill", body=bill or {})


@mcp.tool(name="quickbooks-create-customer", description=_desc("quickbooks-create-customer", "Creates a customer."))
async def quickbooks_create_customer(
    realm_id: Optional[str] = None, customer: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="Customer", body=customer or {})


@mcp.tool(name="quickbooks-create-estimate", description=_desc("quickbooks-create-estimate", "Creates an estimate."))
async def quickbooks_create_estimate(
    realm_id: Optional[str] = None, estimate: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="Estimate", body=estimate or {})


@mcp.tool(name="quickbooks-create-invoice", description=_desc("quickbooks-create-invoice", "Creates an invoice."))
async def quickbooks_create_invoice(
    realm_id: Optional[str] = None, invoice: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="Invoice", body=invoice or {})


@mcp.tool(name="quickbooks-create-payment", description=_desc("quickbooks-create-payment", "Creates a payment."))
async def quickbooks_create_payment(
    realm_id: Optional[str] = None, payment: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="Payment", body=payment or {})


@mcp.tool(name="quickbooks-create-purchase", description=_desc("quickbooks-create-purchase", "Creates a new purchase."))
async def quickbooks_create_purchase(
    realm_id: Optional[str] = None, purchase: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="Purchase", body=purchase or {})


@mcp.tool(
    name="quickbooks-create-purchase-order",
    description=_desc("quickbooks-create-purchase-order", "Creates a purchase order."),
)
async def quickbooks_create_purchase_order(
    realm_id: Optional[str] = None, purchase_order: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="PurchaseOrder", body=purchase_order or {})


@mcp.tool(
    name="quickbooks-create-sales-receipt",
    description=_desc("quickbooks-create-sales-receipt", "Creates a sales receipt."),
)
async def quickbooks_create_sales_receipt(
    realm_id: Optional[str] = None, sales_receipt: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await create_entity(uid, realm_id, entity_name="SalesReceipt", body=sales_receipt or {})


# --- Get / Read ---


@mcp.tool(
    name="quickbooks-get-bill",
    description=_desc("quickbooks-get-bill", "Returns info about a bill."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_bill(realm_id: Optional[str] = None, bill_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="Bill", entity_id=bill_id)


@mcp.tool(
    name="quickbooks-get-customer",
    description=_desc("quickbooks-get-customer", "Returns info about a customer."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_customer(realm_id: Optional[str] = None, customer_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="Customer", entity_id=customer_id)


@mcp.tool(
    name="quickbooks-get-invoice",
    description=_desc("quickbooks-get-invoice", "Returns info about an invoice."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_invoice(realm_id: Optional[str] = None, invoice_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="Invoice", entity_id=invoice_id)


@mcp.tool(
    name="quickbooks-get-payment",
    description=_desc("quickbooks-get-payment", "Returns info about a payment."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_payment(realm_id: Optional[str] = None, payment_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="Payment", entity_id=payment_id)


@mcp.tool(
    name="quickbooks-get-purchase",
    description=_desc("quickbooks-get-purchase", "Returns info about a purchase."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_purchase(realm_id: Optional[str] = None, purchase_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="Purchase", entity_id=purchase_id)


@mcp.tool(
    name="quickbooks-get-purchase-order",
    description=_desc("quickbooks-get-purchase-order", "Returns details about a purchase order."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_purchase_order(realm_id: Optional[str] = None, purchase_order_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="PurchaseOrder", entity_id=purchase_order_id)


@mcp.tool(
    name="quickbooks-get-sales-receipt",
    description=_desc("quickbooks-get-sales-receipt", "Returns details about a sales receipt."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_sales_receipt(realm_id: Optional[str] = None, sales_receipt_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="SalesReceipt", entity_id=sales_receipt_id)


@mcp.tool(
    name="quickbooks-get-time-activity",
    description=_desc("quickbooks-get-time-activity", "Returns info about an activity."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_time_activity(realm_id: Optional[str] = None, time_activity_id: str = "") -> Dict[str, Any]:
    uid = _user_id()
    return await get_entity(uid, realm_id, entity_name="TimeActivity", entity_id=time_activity_id)


@mcp.tool(
    name="quickbooks-get-my-company",
    description=_desc("quickbooks-get-my-company", "Gets info about a company."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_get_my_company(realm_id: Optional[str] = None) -> Dict[str, Any]:
    uid = _user_id()
    # CompanyInfo is a singleton tied to the company. We fetch via query helper.
    return await search_entity(uid, realm_id, entity_name="CompanyInfo", where=None, max_results=1)


# --- Update ---


@mcp.tool(
    name="quickbooks-update-customer",
    description=_desc("quickbooks-update-customer", "Updates a customer."),
)
async def quickbooks_update_customer(
    realm_id: Optional[str] = None, customer: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await update_entity(uid, realm_id, entity_name="Customer", body=customer or {})


@mcp.tool(
    name="quickbooks-update-estimate",
    description=_desc("quickbooks-update-estimate", "Updates an estimate."),
)
async def quickbooks_update_estimate(
    realm_id: Optional[str] = None, estimate: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await update_entity(uid, realm_id, entity_name="Estimate", body=estimate or {})


@mcp.tool(
    name="quickbooks-update-invoice",
    description=_desc("quickbooks-update-invoice", "Updates an invoice."),
)
async def quickbooks_update_invoice(
    realm_id: Optional[str] = None, invoice: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await update_entity(uid, realm_id, entity_name="Invoice", body=invoice or {})


@mcp.tool(
    name="quickbooks-sparse-update-invoice",
    description=_desc("quickbooks-sparse-update-invoice", "Sparse updating provides the ability to update a subset of properties for a given object; only elements specified in the request are updated. Missing elements are left untouched. The ID of the object to update is specified in the request body."),
)
async def quickbooks_sparse_update_invoice(
    realm_id: Optional[str] = None, invoice: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    # Implemented as an "operate" call in your service layer
    return await operate_entity(uid, realm_id, entity_name="Invoice", operation="sparse-update", body=invoice or {})


@mcp.tool(
    name="quickbooks-update-item",
    description=_desc("quickbooks-update-item", "Updates an item."),
)
async def quickbooks_update_item(realm_id: Optional[str] = None, item: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    uid = _user_id()
    return await update_entity(uid, realm_id, entity_name="Item", body=item or {})


# --- Delete / Void / Operate ---


@mcp.tool(
    name="quickbooks-delete-purchase",
    description=_desc("quickbooks-delete-purchase", "Delete a specific purchase."),
    annotations={"destructiveHint": True},
)
async def quickbooks_delete_purchase(realm_id: Optional[str] = None, purchase: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    uid = _user_id()
    # Implemented as an "operate" call in your service layer
    return await operate_entity(uid, realm_id, entity_name="Purchase", operation="delete", body=purchase or {})


@mcp.tool(
    name="quickbooks-void-invoice",
    description=_desc("quickbooks-void-invoice", "Voids an invoice."),
    annotations={"destructiveHint": True},
)
async def quickbooks_void_invoice(realm_id: Optional[str] = None, invoice: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    uid = _user_id()
    return await operate_entity(uid, realm_id, entity_name="Invoice", operation="void", body=invoice or {})


# --- Send ---


@mcp.tool(
    name="quickbooks-send-estimate",
    description=_desc("quickbooks-send-estimate", "Sends an estimate by email."),
)
async def quickbooks_send_estimate(
    realm_id: Optional[str] = None, estimate_id: str = "", send_to: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await send_transaction(uid, realm_id, entity_name="Estimate", entity_id=estimate_id, body=send_to or {})


@mcp.tool(
    name="quickbooks-send-invoice",
    description=_desc("quickbooks-send-invoice", "Sends an invoice by email."),
)
async def quickbooks_send_invoice(
    realm_id: Optional[str] = None, invoice_id: str = "", send_to: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    uid = _user_id()
    return await send_transaction(uid, realm_id, entity_name="Invoice", entity_id=invoice_id, body=send_to or {})


# --- Search / Query ---


@mcp.tool(
    name="quickbooks-search-query",
    description=_desc("quickbooks-search-query", "Performs a search query against a QuickBooks entity."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_query(
    realm_id: Optional[str] = None, sql: str = "", max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    # Uses the same query mechanism as other helpers
    return await query_company(uid, realm_id or "", sql)


@mcp.tool(
    name="quickbooks-search-accounts",
    description=_desc("quickbooks-search-accounts", "Search for accounts."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_accounts(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="Account", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-customers",
    description=_desc("quickbooks-search-customers", "Searches for customers."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_customers(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="Customer", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-invoices",
    description=_desc("quickbooks-search-invoices", "Searches for invoices."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_invoices(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="Invoice", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-sandbox-search-invoices",
    description=_desc("quickbooks-search-invoices", "Searches for invoices."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_sandbox_search_invoices(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    # Kept for compatibility; behaves like invoice search.
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="Invoice", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-items",
    description=_desc("quickbooks-search-items", "Searches for items."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_items(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="Item", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-products",
    description=_desc("quickbooks-search-products", "Search for products."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_products(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    # In QBO, "products" are Items; filter by Type if desired in the where clause.
    return await search_entity(uid, realm_id, entity_name="Item", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-services",
    description=_desc("quickbooks-search-services", "Search for services."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_services(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    # In QBO, "services" are Items; filter by Type=Service in the where clause.
    return await search_entity(uid, realm_id, entity_name="Item", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-purchases",
    description=_desc("quickbooks-search-purchases", "Searches for purchases."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_purchases(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="Purchase", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-time-activities",
    description=_desc("quickbooks-search-time-activities", "Searches for time activities."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_time_activities(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="TimeActivity", where=where, max_results=max_results)


@mcp.tool(
    name="quickbooks-search-vendors",
    description=_desc("quickbooks-search-vendors", "Searches for vendors."),
    annotations={"readOnlyHint": True},
)
async def quickbooks_search_vendors(
    realm_id: Optional[str] = None, where: Optional[str] = None, max_results: int = 10
) -> Dict[str, Any]:
    uid = _user_id()
    return await search_entity(uid, realm_id, entity_name="Vendor", where=where, max_results=max_results)