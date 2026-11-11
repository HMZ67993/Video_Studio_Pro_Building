#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight Windows GUI for HMZ Video Studio Pro manual licensing."""

import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import issue_serial as tool


class LicenseToolGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HMZ Video Studio Pro - License Manager")
        self.geometry("690x590")
        self.minsize(640, 520)
        self.configure(padx=14, pady=12)
        self._build()
        self.refresh_status()

    def _build(self):
        ttk.Label(self, text="HMZ Video Studio Pro", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(self, text="إدارة التراخيص والدفع اليدوي", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, wraplength=650).pack(anchor="w", pady=(0, 10))

        keys = ttk.LabelFrame(self, text="إعداد مفاتيح التوقيع")
        keys.pack(fill="x", pady=5)
        ttk.Button(keys, text="إنشاء المفاتيح لأول مرة", command=self.generate_keys).pack(side="left", padx=8, pady=8)
        ttk.Button(keys, text="إعادة بناء Update.json", command=self.rebuild).pack(side="left", padx=8, pady=8)

        issue = ttk.LabelFrame(self, text="إصدار سيريال يدوي")
        issue.pack(fill="x", pady=5)
        self.machine = tk.StringVar()
        self.customer = tk.StringVar(value="Customer")
        self.validity = tk.StringVar(value="دائم")
        self.days = tk.StringVar(value="30")
        self.expiry = tk.StringVar()
        self._field(issue, "Machine ID للعميل (إجباري لربط الترخيص بجهازه)", self.machine, 0)
        self._field(issue, "اسم العميل", self.customer, 1)
        ttk.Label(issue, text="مدة الترخيص").grid(row=2, column=0, sticky="w", padx=8, pady=5)
        ttk.Combobox(issue, textvariable=self.validity, values=("دائم", "عدد أيام", "حتى تاريخ"), state="readonly", width=18).grid(row=2, column=1, sticky="w", padx=8, pady=5)
        ttk.Label(issue, text="عدد الأيام / تاريخ YYYY-MM-DD").grid(row=3, column=0, sticky="w", padx=8, pady=5)
        ttk.Entry(issue, textvariable=self.days, width=24).grid(row=3, column=1, sticky="w", padx=8, pady=5)
        ttk.Button(issue, text="إصدار السيريال", command=self.issue).grid(row=4, column=0, columnspan=2, pady=8)

        payment = ttk.LabelFrame(self, text="بيانات الدفع التي ستظهر للعميل")
        payment.pack(fill="x", pady=5)
        self.payment_vars = {}
        current = tool.load_state()["payment"]
        labels = [("price", "السعر"), ("bank_name", "البنك"), ("bank_account", "رقم الحساب"),
                  ("instapay", "InstaPay"), ("wallet", "المحفظة"), ("whatsapp", "WhatsApp")]
        for idx, (key, label) in enumerate(labels):
            var = tk.StringVar(value=str(current.get(key, "")))
            self.payment_vars[key] = var
            ttk.Label(payment, text=label).grid(row=idx // 3, column=(idx % 3) * 2, sticky="w", padx=7, pady=5)
            ttk.Entry(payment, textvariable=var, width=22).grid(row=idx // 3, column=(idx % 3) * 2 + 1, sticky="ew", padx=7, pady=5)
        ttk.Button(payment, text="حفظ وتوقيع بيانات الدفع", command=self.save_payment).grid(row=2, column=0, columnspan=6, pady=8)

        revoke = ttk.LabelFrame(self, text="إلغاء ترخيص")
        revoke.pack(fill="x", pady=5)
        self.revoke_value = tk.StringVar()
        ttk.Entry(revoke, textvariable=self.revoke_value).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(revoke, text="إلغاء السيريال", command=self.revoke).pack(side="left", padx=8, pady=8)

        ttk.Button(self, text="عرض السيريالات الصادرة", command=self.list_issued).pack(anchor="e", pady=5)
        self.output = tk.Text(self, height=6, wrap="word", font=("Consolas", 9))
        self.output.pack(fill="both", expand=True, pady=(4, 0))

    def _field(self, parent, label, variable, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
        ttk.Entry(parent, textvariable=variable, width=42).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        parent.columnconfigure(1, weight=1)

    def log(self, value):
        self.output.insert("end", str(value) + "\n")
        self.output.see("end")

    def refresh_status(self):
        exists = all((tool.KEYS_DIR / f"{name}.key").exists() for name in tool.PURPOSES)
        self.status.set("مفاتيح التوقيع: " + ("جاهزة" if exists else "لم تُنشأ بعد — أنشئها مرة واحدة قبل إصدار أي سيريال أو توقيع Update.json."))

    def generate_keys(self):
        if any(tool.KEYS_DIR.glob("*.key")):
            messagebox.showwarning("تنبيه", "توجد مفاتيح بالفعل. لن يتم استبدالها لأن ذلك يبطل السيريالات السابقة.")
            return
        if not messagebox.askyesno("تأكيد", "سيتم إنشاء مفاتيح التوقيع لأول مرة. احتفظ بمجلد tools/keys في مكان آمن ولا ترسله للعملاء. متابعة؟"):
            return
        try:
            tool.cmd_keygen()
            self.log("تم إنشاء المفاتيح وتحديث ملف update.json.")
            self.refresh_status()
            messagebox.showinfo("تم", "تم إنشاء المفاتيح. احتفظ بنسخة احتياطية آمنة من tools/keys.")
        except SystemExit as e:
            messagebox.showerror("خطأ", f"تعذر إنشاء المفاتيح: {e}")

    def require_keys(self):
        if not all((tool.KEYS_DIR / f"{name}.key").exists() for name in tool.PURPOSES):
            messagebox.showerror("المفاتيح غير موجودة", "اضغط «إنشاء المفاتيح لأول مرة» أولًا.")
            return False
        return True

    def issue(self):
        if not self.require_keys():
            return
        machine = self.machine.get().strip()
        if not machine:
            messagebox.showwarning("بيانات ناقصة", "أدخل Machine ID الخاص بالعميل.")
            return
        mode = self.validity.get()
        days, expires = 0, ""
        try:
            if mode == "عدد أيام":
                days = int(self.days.get().strip())
                if days < 1: raise ValueError()
            elif mode == "حتى تاريخ":
                expires = self.days.get().strip()
                datetime.date.fromisoformat(expires)
            serial = tool.cmd_issue(machine, self.customer.get().strip() or "Customer", "", days, expires, "", print_serial=False)
            self.log("السيريال الصادر:\n" + serial)
            self.clipboard_clear()
            self.clipboard_append(serial)
            messagebox.showinfo("تم إصدار السيريال", "تم إنشاء السيريال ونسخه إلى الحافظة.")
        except (ValueError, SystemExit) as e:
            messagebox.showerror("خطأ", f"راجع المدة أو بيانات الترخيص.\n{e}")

    def save_payment(self):
        if not self.require_keys():
            return
        values = {k: v.get().strip() for k, v in self.payment_vars.items()}
        try:
            tool.cmd_sign_payment(**values)
            self.log("تم حفظ بيانات الدفع وتوقيع tools/output/update.json.")
            messagebox.showinfo("تم", "تم توقيع بيانات الدفع وإعادة بناء Update.json.")
        except SystemExit as e:
            messagebox.showerror("خطأ", str(e))

    def rebuild(self):
        if not self.require_keys():
            return
        try:
            out = tool.cmd_build()
            self.log(f"تم إنشاء: {out}")
            messagebox.showinfo("تم", f"تم إنشاء الملف:\n{out}")
        except SystemExit as e:
            messagebox.showerror("خطأ", str(e))

    def revoke(self):
        if not self.require_keys():
            return
        value = self.revoke_value.get().strip()
        if not value:
            return
        try:
            tool.cmd_revoke(jti=value if "." not in value else "", serial=value if "." in value else "")
            self.log("تم إلغاء الترخيص وإعادة بناء Update.json.")
        except SystemExit as e:
            messagebox.showerror("خطأ", str(e))

    def list_issued(self):
        items = tool.load_state().get("issued", [])
        self.log("\n".join(f"{x.get('customer')} | {x.get('machine')} | {x.get('jti')}" for x in items) or "لا توجد سيريالات صادرة بعد.")


if __name__ == "__main__":
    LicenseToolGUI().mainloop()
