"""منطق کسب‌وکار: فاکتورها، انبار، سند خودکار، دفتر اشخاص، چک، ضایعات و گارانتی.

مدل حسابداری دوطرفه است؛ هر رویداد سند خودکار و اثر روی حساب شخص ایجاد می‌کند.
"""
from datetime import datetime

from . import jdate

KINDS = {
    "sale": "فاکتور فروش",
    "proforma": "پیش‌فاکتور فروش",
    "sale_return": "برگشت از فروش",
    "purchase": "فاکتور خرید",
    "purchase_return": "برگشت از خرید",
}
KIND_PREFIX = {
    "sale": "ف", "proforma": "پ", "sale_return": "بف",
    "purchase": "خ", "purchase_return": "بخ",
}
KIND_SIGNS = {
    "sale": -1, "sale_return": +1, "purchase": +1, "purchase_return": -1,
}

ACC = {
    "cash": "صندوق",
    "bank": "بانک",
    "receivable": "حساب‌های دریافتنی",
    "inventory": "موجودی کالا",
    "rec_cheque": "اسناد دریافتنی (چک)",
    "payable": "حساب‌های پرداختنی",
    "pay_cheque": "اسناد پرداختنی (چک)",
    "capital": "سرمایه",
    "sales": "فروش کالا",
    "sales_return": "برگشت از فروش",
    "scrap_sales": "فروش ضایعات باتری",
    "cogs": "بهای تمام‌شده کالای فروش‌رفته",
    "vat_out": "مالیات بر ارزش افزوده پرداختنی",
    "vat_in": "مالیات بر ارزش افزوده خرید",
    "expense": "هزینه‌های عملیاتی",
    "discount": "تخفیف فروش",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def money(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


class Logic:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------- شماره‌گذاری
    def next_number(self, kind):
        prefix = KIND_PREFIX.get(kind, "م")
        year = jdate.jalali_year(jdate.today_str()) % 100
        pre = "{}{}-".format(prefix, year)
        rows = self.db.rows(
            "SELECT number FROM invoices WHERE number LIKE ?", (pre + "%",))
        mx = 0
        for r in rows:
            try:
                mx = max(mx, int(str(r["number"]).split("-")[-1]))
            except ValueError:
                pass
        return "{}{:05d}".format(pre, mx + 1)

    def next_seq(self, table, prefix):
        rows = self.db.rows("SELECT id FROM {} ".format(table))
        n = len(rows) + 1
        return "{}{:05d}".format(prefix, n)

    # ------------------------------------------------------------ ثبت رویدادها
    def log(self, username, action, detail="", entity="", entity_id=None):
        self.db.insert("activity_log", {
            "at": _now(), "username": username or "", "action": action,
            "detail": detail})

    def audit(self, username, action, entity, entity_id, detail=""):
        self.db.insert("audit", {
            "at": _now(), "username": username or "", "action": action,
            "entity": entity, "entity_id": entity_id, "detail": detail})

    # ---------------------------------------------------------------- سند خودکار
    def add_journal(self, date, description, lines, ref_type="", ref_id=None,
                    username=""):
        """lines: فهرست [(account, debit, credit, desc)]"""
        lines = [l for l in lines if abs(money(l[1])) > 1e-9 or abs(money(l[2])) > 1e-9]
        if not lines:
            return None
        number = self.next_seq("journals", "س-")
        jid = self.db.insert("journals", {
            "number": number, "date": date, "description": description,
            "ref_type": ref_type, "ref_id": ref_id, "username": username,
            "created_at": _now()})
        for acc, deb, cred, desc in lines:
            self.db.insert("journal_lines", {
                "journal_id": jid, "account": acc, "debit": money(deb),
                "credit": money(cred), "description": desc or description})
        return jid

    def _party_tx(self, date, party_id, ref_type, ref_id, description, debit=0,
                  credit=0):
        if not party_id:
            return
        self.db.insert("party_tx", {
            "date": date, "party_id": party_id, "ref_type": ref_type,
            "ref_id": ref_id, "description": description,
            "debit": money(debit), "credit": money(credit)})

    # ------------------------------------------------------------------- انبار
    def add_move(self, date, product_id, warehouse_id, qty_in=0, qty_out=0,
                 unit_cost=0, ref_type="", ref_id=None, description=""):
        self.db.insert("stock_moves", {
            "date": date, "product_id": product_id, "warehouse_id": warehouse_id,
            "qty_in": money(qty_in), "qty_out": money(qty_out),
            "unit_cost": money(unit_cost), "ref_type": ref_type, "ref_id": ref_id,
            "description": description, "created_at": _now()})

    def stock_adjust(self, date, product_id, warehouse_id, qty, unit_cost,
                     direction, username, description=""):
        """direction: 'in' یا 'out'"""
        prod = self.db.one("SELECT * FROM products WHERE id=?", (product_id,))
        if not prod:
            raise ValueError("کالا یافت نشد")
        cost = money(unit_cost) or money(prod["purchase_price"])
        if direction == "in":
            self.add_move(date, product_id, warehouse_id, qty_in=qty,
                          unit_cost=cost, ref_type="adjust",
                          description=description or "افزایش موجودی")
            value = money(qty) * cost
            self.add_journal(date, "افزایش موجودی انبار - {}".format(prod["name"]),
                             [(ACC["inventory"], value, 0, "افزایش موجودی"),
                              (ACC["capital"], 0, value, "افزایش موجودی")],
                             ref_type="adjust", username=username)
        else:
            self.add_move(date, product_id, warehouse_id, qty_out=qty,
                          unit_cost=cost, ref_type="adjust",
                          description=description or "کاهش موجودی")
            value = money(qty) * cost
            self.add_journal(date, "کاهش موجودی انبار - {}".format(prod["name"]),
                             [(ACC["expense"], value, 0, "کاهش/ضایعات موجودی"),
                              (ACC["inventory"], 0, value, "کاهش موجودی")],
                             ref_type="adjust", username=username)
        self.audit(username, "اصلاح موجودی", "product", product_id,
                   "{} {} عدد".format(direction, qty))

    def transfer(self, date, product_id, src, dst, qty, username, description=""):
        if qty <= 0:
            raise ValueError("مقدار انتقال باید مثبت باشد")
        avail = self.db.stock_of(product_id, src)
        if qty > avail + 1e-9:
            raise ValueError("موجودی انبار مبدأ کافی نیست (موجودی: {})".format(avail))
        self.add_move(date, product_id, src, qty_out=qty, ref_type="transfer",
                      description=description or "انتقال بین انبار")
        self.add_move(date, product_id, dst, qty_in=qty, ref_type="transfer",
                      description=description or "انتقال بین انبار")
        self.audit(username, "انتقال انبار", "product", product_id,
                   "{} عدد".format(qty))

    # ------------------------------------------------------------------ فاکتورها
    def build_invoice(self, data):
        """محاسبه مبالغ فاکتور بر اساس اقلام (بدون ذخیره)."""
        items = data.get("items") or []
        inv_discount = money(data.get("discount"))
        tax_rate = money(data.get("tax_rate"))
        tax_enabled = str(self.db.get_setting("tax_enabled", "1")) == "1"
        rows = []
        gross_net = 0.0
        for it in items:
            qty = money(it.get("qty"))
            price = money(it.get("unit_price"))
            disc = money(it.get("discount"))
            gross = qty * price
            net = max(gross - disc, 0)
            cost = money(it.get("cost_price"))
            rows.append({"item": it, "qty": qty, "price": price, "disc": disc,
                         "gross": gross, "net": net, "cost": cost})
            gross_net += net
        subtotal = sum(r["gross"] for r in rows)
        items_discount = sum(r["disc"] for r in rows)
        total_discount = items_discount + inv_discount
        allocated = 0.0
        tax_total = 0.0
        cost_total = 0.0
        out_items = []
        for i, r in enumerate(rows):
            if gross_net > 0:
                share = r["net"] / gross_net
            else:
                share = 1.0 / len(rows) if rows else 0
            inv_part = inv_discount * share
            if i == len(rows) - 1:
                inv_part = inv_discount - allocated
            allocated += inv_part
            taxable = max(r["net"] - inv_part, 0)
            rate = money(r["item"].get("tax_rate", tax_rate))
            if not tax_enabled:
                rate = 0
            tax = taxable * rate / 100.0
            line_total = taxable + tax
            tax_total += tax
            cost_total += r["cost"] * r["qty"]
            out_items.append({
                "product_id": r["item"].get("product_id"),
                "description": r["item"].get("description", ""),
                "serial": r["item"].get("serial", ""),
                "warranty_months": int(money(r["item"].get("warranty_months"))),
                "qty": r["qty"], "unit_price": r["price"], "discount": r["disc"],
                "tax_rate": rate, "tax": tax, "total": line_total,
                "cost_price": r["cost"]})
        net_total = subtotal - total_discount
        result = {
            "subtotal": subtotal, "discount": total_discount, "tax": tax_total,
            "total": net_total + tax_total, "cost_total": cost_total,
            "tax_rate": tax_rate, "items": out_items,
        }
        return result

    def save_invoice(self, data, username, invoice_id=None):
        kind = data.get("kind", "sale")
        if kind not in KINDS:
            raise ValueError("نوع فاکتور نامعتبر است")
        calc = self.build_invoice(data)
        if not calc["items"]:
            raise ValueError("فاکتور باید حداقل یک قلم داشته باشد")
        date = data.get("date") or jdate.today_str()
        party_id = data.get("party_id") or None
        warehouse_id = data.get("warehouse_id")
        if not warehouse_id:
            warehouse_id = self.db.scalar(
                "SELECT id FROM warehouses ORDER BY is_default DESC, id LIMIT 1", (), None)

        # موجودی کافی برای فروش/برگشت خرید
        if kind in ("sale", "purchase_return"):
            for it in calc["items"]:
                if not it["product_id"]:
                    continue
                avail = self.db.stock_of(it["product_id"], warehouse_id)
                if it["qty"] > avail + 1e-9:
                    prod = self.db.one("SELECT name FROM products WHERE id=?",
                                       (it["product_id"],))
                    raise ValueError(
                        "موجودی «{}» کافی نیست (موجودی: {}، درخواستی: {})".format(
                            prod["name"] if prod else "", avail, it["qty"]))

        paid_cash = money(data.get("paid_cash"))
        paid_card = money(data.get("paid_card"))
        paid_cheque = money(data.get("paid_cheque"))
        paid = paid_cash + paid_card + paid_cheque
        if paid > calc["total"] + 1e-9:
            raise ValueError("مبلغ پرداختی از مبلغ فاکتور بیشتر است")

        inv = {
            "number": data.get("number") or self.next_number(kind),
            "kind": kind, "date": date, "party_id": party_id,
            "warehouse_id": warehouse_id, "subtotal": calc["subtotal"],
            "discount": calc["discount"], "tax_rate": calc["tax_rate"],
            "tax": calc["tax"], "total": calc["total"],
            "paid_cash": paid_cash, "paid_card": paid_card,
            "paid_cheque": paid_cheque, "cost_total": calc["cost_total"],
            "status": data.get("status", "final"), "note": data.get("note", ""),
            "username": username, "updated_at": _now(),
        }
        if invoice_id:
            old = self.db.one("SELECT * FROM invoices WHERE id=?", (invoice_id,))
            if not old:
                raise ValueError("فاکتور یافت نشد")
            self._reverse_invoice(old, username)
            self.db.update("invoices", invoice_id, inv)
            self.db.conn.execute("DELETE FROM invoice_items WHERE invoice_id=?",
                                 (invoice_id,))
            self.db.conn.commit()
            inv_id = invoice_id
            self.audit(username, "اصلاح فاکتور", "invoice", inv_id, old.get("number", ""))
        else:
            inv["created_at"] = _now()
            inv_id = self.db.insert("invoices", inv)
            self.audit(username, "ثبت فاکتور", "invoice", inv_id, inv["number"])

        for it in calc["items"]:
            it = dict(it)
            it["invoice_id"] = inv_id
            self.db.insert("invoice_items", it)

        if kind != "proforma" and inv["status"] == "final":
            self._apply_invoice(inv_id, inv, calc["items"], username)
        return inv_id

    def _apply_invoice(self, inv_id, inv, items, username):
        kind = inv["kind"]
        date = inv["date"]
        sign = KIND_SIGNS.get(kind, 1)
        wh = inv["warehouse_id"]
        cogs = 0.0
        for it in items:
            if not it["product_id"]:
                continue
            qty = money(it["qty"])
            if sign > 0:
                self.add_move(date, it["product_id"], wh, qty_in=qty,
                              unit_cost=it["cost_price"] or it["unit_price"],
                              ref_type=kind, ref_id=inv_id,
                              description=KINDS[kind])
            else:
                self.add_move(date, it["product_id"], wh, qty_out=qty,
                              unit_cost=it["cost_price"] or it["unit_price"],
                              ref_type=kind, ref_id=inv_id,
                              description=KINDS[kind])
                cogs += money(it["cost_price"]) * qty
            # ثبت سریال باتری برای فروش
            if kind == "sale" and it.get("serial"):
                self._register_serial(it, inv, inv_id)

        net = money(inv["subtotal"]) - money(inv["discount"])
        tax = money(inv["tax"])
        total = money(inv["total"])
        paid_cash = money(inv["paid_cash"])
        paid_card = money(inv["paid_card"])
        paid_cheque = money(inv["paid_cheque"])
        unpaid = total - (paid_cash + paid_card + paid_cheque)
        label = "{} شماره {}".format(KINDS[kind], inv["number"])

        if kind in ("sale", "sale_return"):
            rev_acc = ACC["sales"] if kind == "sale" else ACC["sales_return"]
            cash_acc = ACC["cash"] if kind == "sale" else ACC["cash"]
            rec_acc = ACC["rec_cheque"] if kind == "sale" else ACC["pay_cheque"]
            recv = ACC["receivable"] if kind == "sale" else ACC["payable"]
            lines = [
                (cash_acc, paid_cash, 0, "دریافت نقدی"),
                (ACC["bank"], paid_card, 0, "کارت به کارت"),
                (rec_acc, paid_cheque, 0, "چک"),
                (recv, unpaid, 0, "بدهی شخص"),
                (rev_acc, 0, net if kind == "sale" else 0,
                 "فروش"),
            ]
            if kind == "sale":
                lines.append((ACC["vat_out"], 0, tax, "مالیات فروش"))
                if cogs > 0:
                    lines.append((ACC["cogs"], cogs, 0, "بهای تمام‌شده"))
                    lines.append((ACC["inventory"], 0, cogs, "خروج موجودی"))
            else:
                # برگشت از فروش: فروش کاهش، مالیات کاهش و بدهی شخص کم می‌شود
                lines = [
                    (cash_acc, 0, paid_cash, "برگشت نقدی"),
                    (ACC["bank"], 0, paid_card, "برگشت کارت"),
                    (rec_acc, 0, paid_cheque, "برگشت چک"),
                    (recv, 0, unpaid, "کاهش بدهی شخص"),
                    (ACC["sales_return"], net, 0, "برگشت از فروش"),
                ]
                if tax:
                    lines.append((ACC["vat_out"], tax, 0, "برگشت مالیات فروش"))
                if cogs > 0:
                    lines.append((ACC["inventory"], cogs, 0, "برگشت موجودی"))
                    lines.append((ACC["cogs"], 0, cogs, "برگشت بهای تمام‌شده"))
            self.add_journal(date, label, lines, ref_type=kind, ref_id=inv_id,
                             username=username)
            if kind == "sale":
                self._party_tx(date, inv["party_id"], "invoice", inv_id, label,
                               debit=unpaid)
            else:
                self._party_tx(date, inv["party_id"], "invoice", inv_id, label,
                               credit=unpaid)
        else:  # purchase / purchase_return
            if kind == "purchase":
                lines = [
                    (ACC["inventory"], net, 0, "ورود کالا"),
                    (ACC["vat_in"], tax, 0, "مالیات خرید"),
                    (ACC["cash"], 0, paid_cash, "پرداخت نقدی"),
                    (ACC["bank"], 0, paid_card, "پرداخت کارت"),
                    (ACC["pay_cheque"], 0, paid_cheque, "چک پرداختنی"),
                    (ACC["payable"], 0, unpaid, "بدهی به فروشنده"),
                ]
                self.add_journal(date, label, lines, ref_type=kind, ref_id=inv_id,
                                 username=username)
                self._party_tx(date, inv["party_id"], "invoice", inv_id, label,
                               credit=unpaid)
            else:  # purchase_return
                lines = [
                    (ACC["inventory"], 0, net, "برگشت کالا به فروشنده"),
                    (ACC["vat_in"], 0, tax, "برگشت مالیات خرید"),
                    (ACC["cash"], paid_cash, 0, "دریافت نقدی"),
                    (ACC["bank"], paid_card, 0, "دریافت کارت"),
                    (ACC["pay_cheque"], paid_cheque, 0, "برگشت چک"),
                    (ACC["payable"], unpaid, 0, "کاهش بدهی"),
                ]
                self.add_journal(date, label, lines, ref_type=kind, ref_id=inv_id,
                                 username=username)
                self._party_tx(date, inv["party_id"], "invoice", inv_id, label,
                               debit=unpaid)

    def _register_serial(self, item, inv, inv_id):
        months = int(item.get("warranty_months") or 0)
        prod = self.db.one("SELECT warranty_months FROM products WHERE id=?",
                           (item["product_id"],))
        if prod and prod["warranty_months"]:
            months = months or int(prod["warranty_months"])
        end = jdate.add_months(inv["date"], months) if months else ""
        self.db.insert("battery_serials", {
            "product_id": item["product_id"], "serial": item["serial"],
            "party_id": inv["party_id"], "invoice_id": inv_id, "sold_at": inv["date"],
            "warranty_months": months, "warranty_end": end, "status": "sold",
            "created_at": _now()})

    def _reverse_invoice(self, inv, username):
        """حذف اثرات انبار، سند و دفتر شخصِ فاکتور."""
        inv_id = inv["id"]
        # انبار
        self.db.conn.execute("DELETE FROM stock_moves WHERE ref_type=? AND ref_id=?",
                             (inv["kind"], inv_id))
        # اسناد
        jids = [r["id"] for r in self.db.rows(
            "SELECT id FROM journals WHERE ref_type=? AND ref_id=?",
            (inv["kind"], inv_id))]
        for jid in jids:
            self.db.conn.execute("DELETE FROM journal_lines WHERE journal_id=?",
                                 (jid,))
            self.db.conn.execute("DELETE FROM journals WHERE id=?", (jid,))
        self.db.conn.execute(
            "DELETE FROM party_tx WHERE ref_type='invoice' AND ref_id=?", (inv_id,))
        self.db.conn.execute(
            "DELETE FROM battery_serials WHERE invoice_id=?", (inv_id,))
        self.db.conn.commit()

    def delete_invoice(self, inv_id, username):
        inv = self.db.one("SELECT * FROM invoices WHERE id=?", (inv_id,))
        if not inv:
            raise ValueError("فاکتور یافت نشد")
        self._reverse_invoice(inv, username)
        self.db.conn.execute("DELETE FROM invoice_items WHERE invoice_id=?", (inv_id,))
        self.db.delete("invoices", inv_id)
        self.audit(username, "حذف فاکتور", "invoice", inv_id, inv["number"])
        self.log(username, "حذف فاکتور", inv["number"])

    # ------------------------------------------------------------------- دریافت
    def save_receipt(self, data, username):
        kind = data.get("kind", "receive")
        amount = money(data.get("amount"))
        if amount <= 0:
            raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")
        date = data.get("date") or jdate.today_str()
        number = data.get("number") or self.next_seq("receipts", "ر-")
        rid = self.db.insert("receipts", {
            "number": number, "date": date, "party_id": data.get("party_id") or None,
            "kind": kind, "amount": amount, "method": data.get("method", "cash"),
            "cheque_id": data.get("cheque_id") or None,
            "ref_invoice": data.get("ref_invoice", ""),
            "description": data.get("description", ""), "username": username,
            "created_at": _now()})
        method = data.get("method", "cash")
        acc = ACC["cash"] if method == "cash" else ACC["bank"]
        label = "{} شماره {}".format(
            "دریافت وجه" if kind == "receive" else "پرداخت وجه", number)
        if kind == "receive":
            self.add_journal(date, label,
                             [(acc, amount, 0, "دریافت"), (ACC["receivable"], 0, amount, "کاهش مطالبات")],
                             ref_type="receipt", ref_id=rid, username=username)
            self._party_tx(date, data.get("party_id"), "receipt", rid, label,
                           credit=amount)
        else:
            self.add_journal(date, label,
                             [(ACC["payable"], amount, 0, "کاهش بدهی"), (acc, 0, amount, "پرداخت")],
                             ref_type="receipt", ref_id=rid, username=username)
            self._party_tx(date, data.get("party_id"), "receipt", rid, label,
                           debit=amount)
        return rid

    def delete_receipt(self, rid, username):
        r = self.db.one("SELECT * FROM receipts WHERE id=?", (rid,))
        if not r:
            raise ValueError("سند دریافت/پرداخت یافت نشد")
        jids = [x["id"] for x in self.db.rows(
            "SELECT id FROM journals WHERE ref_type='receipt' AND ref_id=?", (rid,))]
        for jid in jids:
            self.db.conn.execute("DELETE FROM journal_lines WHERE journal_id=?", (jid,))
            self.db.conn.execute("DELETE FROM journals WHERE id=?", (jid,))
        self.db.conn.execute(
            "DELETE FROM party_tx WHERE ref_type='receipt' AND ref_id=?", (rid,))
        self.db.delete("receipts", rid)
        self.db.conn.commit()
        self.audit(username, "حذف دریافت/پرداخت", "receipt", rid, r["number"])

    # ---------------------------------------------------------------------- چک
    def save_cheque(self, data, username, cheque_id=None):
        amount = money(data.get("amount"))
        if amount <= 0:
            raise ValueError("مبلغ چک باید بزرگ‌تر از صفر باشد")
        row = {
            "number": data.get("number", ""), "ctype": data.get("ctype", "receivable"),
            "party_id": data.get("party_id") or None, "bank": data.get("bank", ""),
            "branch": data.get("branch", ""), "account": data.get("account", ""),
            "amount": amount, "issue_date": data.get("issue_date", ""),
            "due_date": data.get("due_date", ""),
            "status": data.get("status", "in_hand"),
            "is_guarantee": 1 if data.get("is_guarantee") else 0,
            "note": data.get("note", ""), "username": username, "updated_at": _now()}
        if cheque_id:
            self.db.update("cheques", cheque_id, row)
            self.audit(username, "اصلاح چک", "cheque", cheque_id, row["number"])
            return cheque_id
        row["created_at"] = _now()
        cid = self.db.insert("cheques", row)
        self.audit(username, "ثبت چک", "cheque", cid, row["number"])
        return cid

    def delete_cheque(self, cid, username):
        self.db.delete("cheques", cid)
        self.audit(username, "حذف چک", "cheque", cid, "")

    # ------------------------------------------------------------------ ضایعات
    def save_scrap(self, data, username):
        """ثبت خرید باتری فرسوده از مشتری."""
        qty = money(data.get("qty"))
        weight = money(data.get("weight_kg"))
        price_kg = money(data.get("price_per_kg"))
        unit_price = money(data.get("unit_price"))
        amount = money(data.get("amount"))
        if amount <= 0:
            amount = (weight * price_kg) + (qty * unit_price)
        if amount <= 0:
            raise ValueError("مبلغ باتری فرسوده باید مشخص شود")
        date = data.get("date") or jdate.today_str()
        method = data.get("method", "cash")
        party_id = data.get("party_id") or None
        wh = data.get("warehouse_id") or self.db.get_setting("scrap_warehouse_id", "2")
        sid = self.db.insert("scrap_batteries", {
            "date": date, "party_id": party_id,
            "product_id": data.get("product_id") or None,
            "brand": data.get("brand", ""), "amperage": data.get("amperage", ""),
            "battery_type": data.get("battery_type", ""), "qty": qty,
            "weight_kg": weight, "price_per_kg": price_kg, "unit_price": unit_price,
            "amount": amount, "method": method, "warehouse_id": wh,
            "ref_invoice_id": data.get("ref_invoice_id") or None,
            "description": data.get("description", ""), "username": username,
            "created_at": _now()})
        label = "خرید باتری فرسوده/ضایعات"
        if method == "cash":
            self.add_journal(date, label,
                             [(ACC["inventory"], amount, 0, "خرید ضایعات"),
                              (ACC["cash"], 0, amount, "پرداخت نقدی")],
                             ref_type="scrap", ref_id=sid, username=username)
        else:
            self.add_journal(date, label,
                             [(ACC["inventory"], amount, 0, "خرید ضایعات"),
                              (ACC["payable"], 0, amount, "بدهی به مشتری")],
                             ref_type="scrap", ref_id=sid, username=username)
            self._party_tx(date, party_id, "scrap", sid, label, credit=amount)
        if party_id and method == "cash":
            # خرید نقدی: برای مشتری اثر بدهی/طلب ندارد
            pass
        self.audit(username, "ثبت باتری فرسوده", "scrap", sid,
                   "{} عدد / {} کیلوگرم".format(qty, weight))
        return sid

    def save_scrap_sale(self, data, username):
        """فروش ضایعات به بازیافت."""
        amount = money(data.get("amount"))
        weight = money(data.get("weight_kg"))
        qty = money(data.get("qty"))
        price_kg = money(data.get("price_per_kg"))
        if amount <= 0:
            amount = weight * price_kg
        if amount <= 0:
            raise ValueError("مبلغ فروش ضایعات باید مشخص شود")
        stock = self.db.scrap_stock()
        if weight and weight > stock["weight"] + 1e-6:
            raise ValueError(
                "موجودی ضایعات کافی نیست (موجودی: {} کیلوگرم)".format(stock["weight"]))
        date = data.get("date") or jdate.today_str()
        method = data.get("method", "cash")
        party_id = data.get("party_id") or None
        sid = self.db.insert("scrap_sales", {
            "date": date, "party_id": party_id, "qty": qty, "weight_kg": weight,
            "price_per_kg": price_kg, "amount": amount, "method": method,
            "description": data.get("description", ""), "username": username,
            "created_at": _now()})
        label = "فروش ضایعات باتری"
        if method == "cash":
            self.add_journal(date, label,
                             [(ACC["cash"], amount, 0, "دریافت نقدی"),
                              (ACC["scrap_sales"], 0, amount, "فروش ضایعات")],
                             ref_type="scrap_sale", ref_id=sid, username=username)
        else:
            self.add_journal(date, label,
                             [(ACC["receivable"], amount, 0, "طلب از بازیافت"),
                              (ACC["scrap_sales"], 0, amount, "فروش ضایعات")],
                             ref_type="scrap_sale", ref_id=sid, username=username)
            self._party_tx(date, party_id, "scrap_sale", sid, label, debit=amount)
        self.audit(username, "فروش ضایعات", "scrap_sale", sid,
                   "{} کیلوگرم".format(weight))
        return sid

    def allocate_scrap_out(self, weight):
        """کاهش مقدار خارج‌شده از انبار ضایعات (تخصیص FIFO ساده)."""
        remaining = weight
        rows = self.db.rows(
            "SELECT id, qty, weight_kg, out_qty, out_weight FROM scrap_batteries "
            "WHERE weight_kg > out_weight ORDER BY date, id")
        for r in rows:
            if remaining <= 1e-9:
                break
            avail = money(r["weight_kg"]) - money(r["out_weight"])
            take = min(avail, remaining)
            ratio = take / money(r["weight_kg"]) if money(r["weight_kg"]) else 0
            self.db.conn.execute(
                "UPDATE scrap_batteries SET out_weight=out_weight+?, "
                "out_qty=out_qty+? WHERE id=?",
                (take, money(r["qty"]) * ratio, r["id"]))
            remaining -= take
        self.db.conn.commit()

    # ------------------------------------------------------------------ گارانتی
    def warranty_claim(self, serial_id, username, note=""):
        s = self.db.one("SELECT * FROM battery_serials WHERE id=?", (serial_id,))
        if not s:
            raise ValueError("سریال باتری یافت نشد")
        self.db.update("battery_serials", serial_id,
                       {"status": "returned", "note": note or "مرجوعی گارانتی"})
        self.audit(username, "مرجوعی گارانتی", "serial", serial_id, s["serial"])
        return serial_id

    def serial_to_scrap(self, serial_id, data, username):
        """تبدیل باتری فرسوده‌شده/مرجوعی به ضایعات."""
        s = self.db.one("SELECT * FROM battery_serials WHERE id=?", (serial_id,))
        if not s:
            raise ValueError("سریال باتری یافت نشد")
        prod = self.db.one("SELECT * FROM products WHERE id=?", (s["product_id"],))
        d = dict(data)
        d.setdefault("brand", prod["brand"] if prod else "")
        d.setdefault("amperage", prod["amperage"] if prod else "")
        d.setdefault("qty", 1)
        sid = self.save_scrap(d, username)
        self.db.update("battery_serials", serial_id,
                       {"status": "scrap", "note": "تبدیل به ضایعات"})
        return sid

    # ------------------------------------------------------------------- دفترها
    def party_balance(self, party_id):
        p = self.db.one("SELECT * FROM parties WHERE id=?", (party_id,))
        if not p:
            return 0.0
        deb = self.db.scalar(
            "SELECT COALESCE(SUM(debit),0) FROM party_tx WHERE party_id=?",
            (party_id,), 0)
        cred = self.db.scalar(
            "SELECT COALESCE(SUM(credit),0) FROM party_tx WHERE party_id=?",
            (party_id,), 0)
        return money(p["opening_balance"]) + money(deb) - money(cred)

    def party_ledger(self, party_id):
        rows = self.db.rows(
            "SELECT * FROM party_tx WHERE party_id=? ORDER BY date, id", (party_id,))
        p = self.db.one("SELECT * FROM parties WHERE id=?", (party_id,))
        bal = money(p["opening_balance"]) if p else 0
        out = []
        if p and money(p["opening_balance"]):
            out.append({"date": "", "description": "مانده اول دوره",
                        "debit": money(p["opening_balance"]) if p["opening_balance"] > 0 else 0,
                        "credit": abs(money(p["opening_balance"])) if p["opening_balance"] < 0 else 0,
                        "balance": bal})
        for r in rows:
            bal += money(r["debit"]) - money(r["credit"])
            out.append({"date": r["date"], "description": r["description"],
                        "debit": r["debit"], "credit": r["credit"], "balance": bal})
        return out

    # ------------------------------------------------------------------ گزارش‌ها
    def account_balances(self):
        rows = self.db.rows(
            "SELECT account, COALESCE(SUM(debit),0) AS debit, "
            "COALESCE(SUM(credit),0) AS credit FROM journal_lines GROUP BY account")
        accs = self.db.rows("SELECT * FROM accounts")
        atype = {a["name"]: a["atype"] for a in accs}
        out = []
        for r in rows:
            out.append({"account": r["account"], "debit": r["debit"],
                        "credit": r["credit"], "balance": r["debit"] - r["credit"],
                        "type": atype.get(r["account"], "")})
        return out

    def trial_balance(self):
        return self.account_balances()

    def profit_loss(self, date_from=None, date_to=None):
        where, params = self._date_where("j.date", date_from, date_to)
        rows = self.db.rows(
            "SELECT jl.account, COALESCE(SUM(jl.debit),0) d, "
            "COALESCE(SUM(jl.credit),0) c FROM journal_lines jl "
            "JOIN journals j ON j.id=jl.journal_id {} GROUP BY jl.account".format(where),
            params)
        accs = self.db.rows("SELECT * FROM accounts")
        atype = {a["name"]: a["atype"] for a in accs}
        revenue, expense = [], []
        for r in rows:
            bal = r["d"] - r["c"]
            t = atype.get(r["account"], "")
            if t == "revenue":
                revenue.append({"account": r["account"], "amount": -bal})
            elif t == "expense":
                expense.append({"account": r["account"], "amount": bal})
        total_rev = sum(x["amount"] for x in revenue)
        total_exp = sum(x["amount"] for x in expense)
        return {"revenue": revenue, "expense": expense, "total_revenue": total_rev,
                "total_expense": total_exp, "profit": total_rev - total_exp}

    def _date_where(self, col, date_from, date_to):
        conds, params = [], []
        if date_from:
            conds.append("{} >= ?".format(col))
            params.append(date_from)
        if date_to:
            conds.append("{} <= ?".format(col))
            params.append(date_to)
        return ("WHERE " + " AND ".join(conds)) if conds else "", params

    def balance_sheet(self, date_to=None):
        balances = {b["account"]: b["balance"] for b in self.account_balances()}
        inv_value = self.db.scalar(
            "SELECT COALESCE(SUM((qty_in-qty_out)*unit_cost),0) FROM stock_moves")
        scrap_value = self.db.scrap_stock()["value"]
        assets = [
            {"account": ACC["cash"], "amount": balances.get(ACC["cash"], 0)},
            {"account": ACC["bank"], "amount": balances.get(ACC["bank"], 0)},
            {"account": ACC["receivable"], "amount": balances.get(ACC["receivable"], 0)},
            {"account": ACC["rec_cheque"], "amount": balances.get(ACC["rec_cheque"], 0)},
            {"account": ACC["vat_in"], "amount": balances.get(ACC["vat_in"], 0)},
            {"account": "موجودی انبار", "amount": money(inv_value)},
            {"account": "موجودی ضایعات", "amount": money(scrap_value)},
        ]
        liabilities = [
            {"account": ACC["payable"], "amount": -balances.get(ACC["payable"], 0)},
            {"account": ACC["pay_cheque"], "amount": -balances.get(ACC["pay_cheque"], 0)},
            {"account": ACC["vat_out"], "amount": -balances.get(ACC["vat_out"], 0)},
        ]
        ta = sum(a["amount"] for a in assets)
        tl = sum(l["amount"] for l in liabilities)
        equity = ta - tl
        return {"assets": assets, "liabilities": liabilities,
                "total_assets": ta, "total_liabilities": tl,
                "equity": equity}

    def sales_summary(self, date_from=None, date_to=None):
        where, params = self._date_where("date", date_from, date_to)
        rows = self.db.rows(
            "SELECT kind, COUNT(*) c, COALESCE(SUM(total),0) t, "
            "COALESCE(SUM(cost_total),0) cost FROM invoices {} "
            "GROUP BY kind".format(where), params)
        return rows

    def product_sales(self, date_from=None, date_to=None, limit=50):
        where, params = self._date_where("i.date", date_from, date_to)
        rows = self.db.rows(
            "SELECT ii.product_id, p.name, COALESCE(SUM(ii.qty),0) qty, "
            "COALESCE(SUM(ii.total),0) total, COALESCE(SUM(ii.qty*ii.cost_price),0) cost "
            "FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id "
            "LEFT JOIN products p ON p.id=ii.product_id "
            "WHERE i.kind='sale' {} GROUP BY ii.product_id ORDER BY total DESC LIMIT ?"
            .format(where.replace("WHERE", "AND", 1) if where else ""),
            params + [limit])
        return rows

    def debtors(self):
        rows = self.db.rows("SELECT * FROM parties WHERE active=1")
        out = []
        for p in rows:
            bal = self.party_balance(p["id"])
            if abs(bal) > 0.5:
                out.append({"id": p["id"], "name": p["name"], "phone": p["phone"],
                            "mobile": p["mobile"], "balance": bal})
        out.sort(key=lambda x: -x["balance"])
        return out

    def cheque_due(self, days=30):
        today = jdate.today_str()
        rows = self.db.rows(
            "SELECT c.*, p.name AS party_name FROM cheques c "
            "LEFT JOIN parties p ON p.id=c.party_id "
            "WHERE c.status NOT IN ('cleared','returned') "
            "AND c.is_guarantee=0 ORDER BY c.due_date")
        out = []
        for r in rows:
            if not r["due_date"]:
                continue
            d = jdate.diff_days(today, r["due_date"])
            r["days_left"] = d
            if d <= days:
                out.append(r)
        return out

    def inventory_report(self):
        rows = self.db.rows(
            "SELECT p.*, g.name AS group_name, u.name AS unit_name, "
            "(SELECT COALESCE(SUM(qty_in-qty_out),0) FROM stock_moves m "
            " WHERE m.product_id=p.id) AS stock FROM products p "
            "LEFT JOIN product_groups g ON g.id=p.group_id "
            "LEFT JOIN units u ON u.id=p.unit_id WHERE p.active=1 ORDER BY p.name")
        for r in rows:
            r["value"] = money(r["stock"]) * money(r["purchase_price"])
            r["low"] = money(r["stock"]) <= money(r["reorder_level"])
        return rows
