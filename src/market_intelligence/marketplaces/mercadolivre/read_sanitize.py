from __future__ import annotations
from typing import Any
def safe_user(p:dict[str,Any])->dict[str,Any]:return {k:p.get(k) for k in ("id","site_id","nickname","status","seller_reputation","tags") if k in p}
def safe_item(p:dict[str,Any])->dict[str,Any]:
    keep=("id","site_id","title","subtitle","seller_id","category_id","official_store_id","price","base_price","original_price","currency_id","initial_quantity","available_quantity","sold_quantity","sale_terms","buying_mode","listing_type_id","start_time","stop_time","condition","permalink","thumbnail","secure_thumbnail","pictures","video_id","accepts_mercadopago","non_mercado_pago_payment_methods","shipping","attributes","status","sub_status","tags","warranty","catalog_product_id","domain_id","seller_custom_field","variations","catalog_listing","health","user_product_id")
    return {k:p.get(k) for k in keep if k in p}
def safe_items_search(p:dict[str,Any])->dict[str,Any]:return {k:p.get(k) for k in ("seller_id","results","paging","query","orders","available_orders") if k in p}
def safe_order(o:dict[str,Any])->dict[str,Any]:
    rows=[]
    for r in o.get("order_items") or []:
        if not isinstance(r,dict):continue
        item=r.get("item") if isinstance(r.get("item"),dict) else {}
        rows.append({"item_id":item.get("id"),"title":item.get("title"),"seller_sku":item.get("seller_sku"),"quantity":r.get("quantity"),"unit_price":r.get("unit_price"),"currency_id":r.get("currency_id"),"full_unit_price":r.get("full_unit_price")})
    shipping=o.get("shipping") if isinstance(o.get("shipping"),dict) else {}
    return {"id":o.get("id"),"status":o.get("status"),"status_detail":o.get("status_detail"),"date_created":o.get("date_created"),"date_closed":o.get("date_closed"),"last_updated":o.get("last_updated"),"total_amount":o.get("total_amount"),"paid_amount":o.get("paid_amount"),"currency_id":o.get("currency_id"),"order_items":rows,"shipping_id":shipping.get("id"),"tags":o.get("tags")}
def safe_orders_search(p:dict[str,Any])->dict[str,Any]:return {"results":[safe_order(r) for r in p.get("results") or [] if isinstance(r,dict)],"paging":p.get("paging"),"sort":p.get("sort")}
def safe_questions(p:dict[str,Any])->dict[str,Any]:
    rows=[]
    for q in p.get("questions") or []:
        if not isinstance(q,dict):continue
        a=q.get("answer") if isinstance(q.get("answer"),dict) else None
        rows.append({"id":q.get("id"),"item_id":q.get("item_id"),"status":q.get("status"),"date_created":q.get("date_created"),"answer":({"status":a.get("status"),"date_created":a.get("date_created")} if a else None)})
    return {"total":p.get("total"),"limit":p.get("limit"),"questions":rows}
def safe_claims(p:dict[str,Any])->dict[str,Any]:return {"paging":p.get("paging"),"data":[{k:c.get(k) for k in ("id","resource_id","status","type","stage","parent_id","resource","reason_id","fulfilled")} for c in p.get("data") or [] if isinstance(c,dict)]}
