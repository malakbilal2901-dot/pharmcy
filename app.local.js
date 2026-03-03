(() => {
  const STORAGE_KEYS = {
    theme: "pharma_theme_v1",
    products: "pharma_products_v1",
    customerDebts: "pharma_customer_debts_v1",
    supplierDebts: "pharma_supplier_debts_v1"
  };

  const DEFAULT_PRODUCTS = [
    {
      id: "p1",
      name: "بانادول",
      gtin: "6281001234567",
      price: 15,
      cost: 10,
      qty: 40,
      batch: "PAN-2026-01",
      expiry: "2027-06-30",
      vat: 15,
      manufacturer: "GSK",
      supplier: "النهدي"
    },
    {
      id: "p2",
      name: "فيتامين C",
      gtin: "6281007654321",
      price: 28,
      cost: 20,
      qty: 22,
      batch: "VITC-2026-03",
      expiry: "2027-12-31",
      vat: 15,
      manufacturer: "Jamjoom",
      supplier: "سقالة"
    },
    {
      id: "p3",
      name: "أوجمنتين 625",
      gtin: "6281009876543",
      price: 42,
      cost: 31,
      qty: 18,
      batch: "AUG-2026-08",
      expiry: "2027-09-30",
      vat: 15,
      manufacturer: "GSK",
      supplier: "تامر"
    }
  ];

  const DEFAULT_CUSTOMER_DEBTS = [
    {
      id: "cd1",
      customer: "عيادة النور",
      phone: "0501234567",
      amount: 1250,
      createdAt: "2026-03-01",
      status: "open",
      notes: "توريد أسبوعي"
    },
    {
      id: "cd2",
      customer: "مركز الشفاء",
      phone: "0559876543",
      amount: 680,
      createdAt: "2026-03-02",
      status: "open",
      notes: "صرف آجل"
    }
  ];

  const DEFAULT_SUPPLIER_DEBTS = [
    {
      id: "sd1",
      supplier: "تامر",
      phone: "920000111",
      amount: 4200,
      dueDate: "2026-03-10",
      status: "due",
      notes: "طلبية مضادات حيوية"
    },
    {
      id: "sd2",
      supplier: "سقالة",
      phone: "920000222",
      amount: 1950,
      dueDate: "2026-03-07",
      status: "due",
      notes: "مكملات غذائية"
    }
  ];

  function formatMoney(value) {
    return `${Number(value || 0).toFixed(2)} ر.س`;
  }

  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  function debtStatusLabel(status) {
    if (status === "paid") return "مسدد";
    if (status === "overdue") return "متأخر";
    return "قائم";
  }

  class PharmaApp {
    constructor() {
      this.products = this.load(STORAGE_KEYS.products, DEFAULT_PRODUCTS);
      this.customerDebts = this.load(STORAGE_KEYS.customerDebts, DEFAULT_CUSTOMER_DEBTS);
      this.supplierDebts = this.load(STORAGE_KEYS.supplierDebts, DEFAULT_SUPPLIER_DEBTS);
      this.cart = [];
      this.editingProductId = null;

      this.grid = document.getElementById("pos-products-grid");
      this.tableBody = document.getElementById("inventory-table-body");
      this.cartItems = document.getElementById("pos-cart-items");
      this.totalEl = document.getElementById("pos-total");
      this.vatEl = document.getElementById("pos-vat");
      this.titleEl = document.getElementById("page-title");
      this.themeStatusEl = document.getElementById("theme-status");

      this.initTheme();
      this.buildCustomerDebtModal();
      this.injectPosDebtButton();
      this.renderAll();
      this.renderFinanceDebtCenter();
      this.renderSupplierDebtCenter();
    }

    load(key, fallback) {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) return structuredClone(fallback);
        return JSON.parse(raw);
      } catch {
        return structuredClone(fallback);
      }
    }

    save(key, value) {
      localStorage.setItem(key, JSON.stringify(value));
    }

    initTheme() {
      const theme = localStorage.getItem(STORAGE_KEYS.theme) || "light";
      document.body.classList.toggle("dark", theme === "dark");
      this.themeStatusEl.textContent = theme === "dark" ? "الوضع الليلي" : "الوضع النهاري";
    }

    toggleTheme() {
      const isDark = document.body.classList.toggle("dark");
      localStorage.setItem(STORAGE_KEYS.theme, isDark ? "dark" : "light");
      this.themeStatusEl.textContent = isDark ? "الوضع الليلي" : "الوضع النهاري";
    }

    nav(section) {
      document.querySelectorAll(".section-content").forEach((sec) => sec.classList.remove("active"));
      document.getElementById(`sec-${section}`)?.classList.add("active");

      document.querySelectorAll(".sidebar-link").forEach((item) => item.classList.remove("active"));
      document.getElementById(`link-${section}`)?.classList.add("active");

      const titles = {
        pos: "كاشير البيع السريع",
        inventory: "إدارة المخزون",
        procurement: "المشتريات والموردين",
        insurance: "التأمين ووصفتي",
        admin: "لوحة الإدارة",
        hr: "شؤون الموظفين",
        finance: "التقارير المالية"
      };
      this.titleEl.textContent = titles[section] || "PharmaOS";

      if (window.innerWidth < 1024) {
        document.body.classList.remove("sidebar-open");
        document.getElementById("sidebar-backdrop")?.classList.add("hidden");
      }
    }

    getCartTotals() {
      const subtotal = this.cart.reduce((sum, item) => sum + item.price * item.qty, 0);
      const vat = this.cart.reduce((sum, item) => sum + item.price * item.qty * ((item.vat || 15) / 100), 0);
      return { subtotal, vat, total: subtotal + vat };
    }

    renderAll() {
      this.renderProductsGrid();
      this.renderInventoryTable();
      this.renderCart();
      this.renderFinanceDebtCenter();
      this.renderSupplierDebtCenter();
    }

    renderProductsGrid() {
      this.grid.innerHTML = this.products
        .map((product) => {
          const qtyColor = product.qty <= 5 ? "text-red-500" : "text-emerald-600";
          return `
            <div class="glass-panel rounded-2xl p-4 border border-slate-200 dark:border-slate-700">
              <h4 class="font-bold mb-2">${product.name}</h4>
              <p class="text-xs text-slate-400 mb-1">GTIN: ${product.gtin}</p>
              <p class="text-sm mb-2">السعر: <span class="font-bold text-emerald-600">${formatMoney(product.price)}</span></p>
              <p class="text-xs ${qtyColor} mb-3">المتوفر: ${product.qty}</p>
              <button onclick="app.addToCart('${product.id}')" class="w-full bg-emerald-500 text-white py-2 rounded-xl text-sm font-bold">إضافة للفاتورة</button>
            </div>
          `;
        })
        .join("");
    }

    renderInventoryTable() {
      this.tableBody.innerHTML = this.products
        .map(
          (product) => `
            <tr>
              <td class="p-4 font-bold">${product.name}</td>
              <td class="p-4">${product.gtin}</td>
              <td class="p-4">${product.batch}</td>
              <td class="p-4">${product.expiry}</td>
              <td class="p-4">${product.qty}</td>
              <td class="p-4">${formatMoney(product.cost)}</td>
              <td class="p-4">
                <div class="flex gap-2">
                  <button onclick="app.openAddProductModal('${product.id}')" class="text-xs bg-blue-500 text-white px-3 py-1 rounded-lg">تعديل</button>
                  <button onclick="app.deleteProduct('${product.id}')" class="text-xs bg-red-500 text-white px-3 py-1 rounded-lg">حذف</button>
                </div>
              </td>
            </tr>
          `
        )
        .join("");
    }

    addToCart(productId) {
      const product = this.products.find((p) => p.id === productId);
      if (!product) return;
      if (product.qty <= 0) {
        this.toast("الكمية غير متاحة", "error");
        return;
      }

      const existing = this.cart.find((item) => item.id === productId);
      if (existing) {
        existing.qty += 1;
      } else {
        this.cart.push({ id: product.id, name: product.name, price: product.price, vat: product.vat || 15, qty: 1 });
      }
      product.qty -= 1;
      this.save(STORAGE_KEYS.products, this.products);
      this.renderAll();
    }

    removeFromCart(productId) {
      const idx = this.cart.findIndex((item) => item.id === productId);
      if (idx < 0) return;
      const item = this.cart[idx];
      const product = this.products.find((p) => p.id === productId);
      if (product) product.qty += 1;

      item.qty -= 1;
      if (item.qty <= 0) this.cart.splice(idx, 1);
      this.save(STORAGE_KEYS.products, this.products);
      this.renderAll();
    }

    renderCart() {
      if (!this.cart.length) {
        this.cartItems.innerHTML = '<p class="text-xs text-slate-400">لا توجد أصناف في الفاتورة</p>';
      } else {
        this.cartItems.innerHTML = this.cart
          .map(
            (item) => `
              <div class="flex justify-between items-center bg-slate-50 dark:bg-slate-800 p-3 rounded-xl">
                <div>
                  <p class="font-bold">${item.name}</p>
                  <p class="text-xs text-slate-400">${item.qty} x ${formatMoney(item.price)}</p>
                </div>
                <button onclick="app.removeFromCart('${item.id}')" class="text-red-500 text-sm font-bold">حذف</button>
              </div>
            `
          )
          .join("");
      }

      const totals = this.getCartTotals();
      this.vatEl.textContent = totals.vat.toFixed(2);
      this.totalEl.textContent = formatMoney(totals.total);
    }

    completeSale() {
      if (!this.cart.length) {
        this.toast("أضف منتج واحد على الأقل", "error");
        return;
      }
      this.cart = [];
      this.renderCart();
      this.toast("تمت عملية البيع بنجاح", "success");
    }

    injectPosDebtButton() {
      if (document.getElementById("defer-sale-btn")) return;
      const payButton = document.querySelector('button[onclick="app.completeSale()"]');
      if (!payButton || !payButton.parentElement) return;

      const debtBtn = document.createElement("button");
      debtBtn.id = "defer-sale-btn";
      debtBtn.type = "button";
      debtBtn.setAttribute("onclick", "app.deferSaleAsDebt()");
      debtBtn.className = "w-full bg-orange-500 text-white p-3 rounded-2xl font-bold";
      debtBtn.textContent = "تأجيل دين للعميل";
      payButton.parentElement.insertBefore(debtBtn, payButton);
    }

    buildCustomerDebtModal() {
      if (document.getElementById("customer-debt-modal")) return;
      const modal = document.createElement("div");
      modal.id = "customer-debt-modal";
      modal.className = "fixed inset-0 bg-slate-900/70 backdrop-blur-sm hidden items-center justify-center z-[120]";
      modal.innerHTML = `
        <div class="glass-panel p-8 rounded-[32px] w-full max-w-xl shadow-2xl">
          <div class="flex justify-between items-center mb-5 border-b border-slate-200 dark:border-slate-700 pb-3">
            <h3 class="text-xl font-bold text-orange-500">تأجيل فاتورة كدين عميل</h3>
            <button type="button" onclick="app.closeCustomerDebtModal()" class="text-slate-400 hover:text-red-500"><i class="fas fa-times"></i></button>
          </div>
          <form id="customer-debt-form" onsubmit="app.saveCustomerDebt(event)" class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="md:col-span-2">
              <label class="block text-xs font-bold text-slate-500 mb-1">اسم العميل</label>
              <input name="customer" required class="w-full bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none focus:border-orange-500 transition" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-500 mb-1">رقم الجوال</label>
              <input name="phone" required class="w-full bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none focus:border-orange-500 transition" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-500 mb-1">المبلغ</label>
              <input id="customer-debt-amount" name="amount" type="number" step="0.01" min="0.01" required class="w-full bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none focus:border-orange-500 transition" />
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs font-bold text-slate-500 mb-1">ملاحظات</label>
              <input name="notes" placeholder="مثال: صرف عاجل - متابعة بعد 3 أيام" class="w-full bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none focus:border-orange-500 transition" />
            </div>
            <div class="md:col-span-2 flex gap-3 mt-2">
              <button type="button" onclick="app.closeCustomerDebtModal()" class="flex-1 py-3 rounded-xl font-bold text-slate-500 border border-slate-200 dark:border-slate-700">إلغاء</button>
              <button type="submit" class="flex-1 bg-orange-500 text-white py-3 rounded-xl font-bold">حفظ الدين وإغلاق الفاتورة</button>
            </div>
          </form>
        </div>
      `;
      document.body.appendChild(modal);
    }

    deferSaleAsDebt() {
      if (!this.cart.length) {
        this.toast("الفاتورة فاضية", "error");
        return;
      }
      const modal = document.getElementById("customer-debt-modal");
      const amountInput = document.getElementById("customer-debt-amount");
      if (amountInput) {
        amountInput.value = this.getCartTotals().total.toFixed(2);
      }
      modal.classList.remove("hidden");
      modal.classList.add("flex");
      document.body.classList.add("modal-open");
    }

    closeCustomerDebtModal() {
      const modal = document.getElementById("customer-debt-modal");
      modal.classList.remove("flex");
      modal.classList.add("hidden");
      document.body.classList.remove("modal-open");
    }

    saveCustomerDebt(event) {
      event.preventDefault();
      if (!this.cart.length) {
        this.closeCustomerDebtModal();
        this.toast("الفاتورة فاضية", "error");
        return;
      }

      const formData = new FormData(event.target);
      const amount = Number(formData.get("amount") || 0);
      const customer = String(formData.get("customer") || "").trim();
      const phone = String(formData.get("phone") || "").trim();
      const notes = String(formData.get("notes") || "").trim();

      if (!customer || !phone || amount <= 0) {
        this.toast("بيانات الدين غير مكتملة", "error");
        return;
      }

      this.customerDebts.unshift({
        id: `cd_${Date.now()}`,
        customer,
        phone,
        amount,
        createdAt: todayISO(),
        status: "open",
        notes
      });
      this.save(STORAGE_KEYS.customerDebts, this.customerDebts);

      this.cart = [];
      event.target.reset();
      this.closeCustomerDebtModal();
      this.renderAll();
      this.toast("تم حفظ الدين على العميل", "success");
    }

    collectCustomerDebtPrompt(debtId) {
      const debt = this.customerDebts.find((d) => d.id === debtId);
      if (!debt || debt.status === "paid") return;

      const paidRaw = prompt(`المتبقي على ${debt.customer}: ${debt.amount.toFixed(2)}\nاكتب مبلغ التحصيل:`);
      if (paidRaw === null) return;
      const paid = Number(paidRaw);
      if (!Number.isFinite(paid) || paid <= 0) {
        this.toast("مبلغ غير صالح", "error");
        return;
      }

      debt.amount = Math.max(0, Number((debt.amount - paid).toFixed(2)));
      debt.status = debt.amount === 0 ? "paid" : "open";
      this.save(STORAGE_KEYS.customerDebts, this.customerDebts);
      this.renderFinanceDebtCenter();
      this.toast(debt.status === "paid" ? "تم سداد الدين بالكامل" : "تم تسجيل دفعة جزئية", "success");
    }

    renderFinanceDebtCenter() {
      const financeSection = document.getElementById("sec-finance");
      if (!financeSection) return;

      const oldCard = document.getElementById("debts-card");
      oldCard?.remove();

      const totalOpen = this.customerDebts
        .filter((d) => d.status !== "paid")
        .reduce((sum, d) => sum + Number(d.amount || 0), 0);
      const totalPaidCount = this.customerDebts.filter((d) => d.status === "paid").length;

      const card = document.createElement("div");
      card.id = "debts-card";
      card.className = "glass-panel p-6 rounded-3xl md:col-span-3";
      card.innerHTML = `
        <div class="flex flex-wrap justify-between gap-3 items-center mb-4">
          <div>
            <p class="text-xs text-slate-400">مركز ديون العملاء</p>
            <h3 class="text-xl font-black text-orange-500">إجمالي القائم: <span class="masked">${formatMoney(totalOpen)}</span></h3>
          </div>
          <div class="text-xs text-slate-400">ديون مسددة: ${totalPaidCount}</div>
        </div>
        <div class="mb-4">
          <input id="customer-debt-search" placeholder="بحث باسم العميل أو رقمه" class="w-full bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none" />
        </div>
        <div id="customer-debt-list" class="space-y-2 max-h-64 overflow-y-auto"></div>
      `;
      financeSection.appendChild(card);

      const renderList = (query = "") => {
        const list = card.querySelector("#customer-debt-list");
        const q = query.trim().toLowerCase();
        const rows = this.customerDebts.filter((d) => {
          if (!q) return true;
          return d.customer.toLowerCase().includes(q) || d.phone.includes(q);
        });

        list.innerHTML = rows.length
          ? rows
              .map((d) => `
                <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
                  <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div>
                      <p class="font-bold">${d.customer}</p>
                      <p class="text-xs text-slate-400">${d.phone} | ${d.createdAt}</p>
                    </div>
                    <span class="text-xs px-2 py-1 rounded-full ${d.status === "paid" ? "bg-emerald-100 text-emerald-700" : "bg-orange-100 text-orange-700"}">${debtStatusLabel(d.status)}</span>
                  </div>
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <p class="font-black text-orange-500 masked">${formatMoney(d.amount)}</p>
                    <div class="flex gap-2">
                      <button onclick="app.collectCustomerDebtPrompt('${d.id}')" class="text-xs px-3 py-1 rounded-lg bg-blue-500 text-white">تحصيل دفعة</button>
                    </div>
                  </div>
                  ${d.notes ? `<p class="text-[11px] text-slate-500 mt-2">ملاحظة: ${d.notes}</p>` : ""}
                </div>
              `)
              .join("")
          : '<p class="text-xs text-slate-400">لا توجد نتائج</p>';
      };

      renderList();
      card.querySelector("#customer-debt-search")?.addEventListener("input", (e) => {
        renderList(e.target.value || "");
      });
    }

    renderSupplierDebtCenter() {
      const procurementSection = document.getElementById("sec-procurement");
      if (!procurementSection) return;

      const oldWrap = document.getElementById("supplier-debt-center");
      oldWrap?.remove();

      const totalDue = this.supplierDebts
        .filter((d) => d.status !== "paid")
        .reduce((sum, d) => sum + Number(d.amount || 0), 0);

      const wrap = document.createElement("div");
      wrap.id = "supplier-debt-center";
      wrap.className = "grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6";

      wrap.innerHTML = `
        <div class="glass-panel p-6 rounded-3xl">
          <h3 class="font-bold mb-4 text-orange-500">إضافة دين مورد</h3>
          <form id="supplier-debt-form" class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input name="supplier" placeholder="اسم المورد" required class="md:col-span-2 bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none" />
            <input name="phone" placeholder="رقم المورد" required class="bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none" />
            <input name="amount" type="number" step="0.01" min="0.01" placeholder="المبلغ" required class="bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none" />
            <input name="dueDate" type="date" required class="bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none" />
            <input name="notes" placeholder="ملاحظات" class="md:col-span-2 bg-slate-50 border border-slate-200 dark:border-slate-700 rounded-xl p-3 outline-none" />
            <button type="submit" class="md:col-span-2 bg-orange-500 text-white py-3 rounded-xl font-bold">إضافة للمركز</button>
          </form>
        </div>
        <div class="glass-panel p-6 rounded-3xl">
          <div class="flex justify-between items-center mb-3">
            <h3 class="font-bold">مركز ديون الموردين</h3>
            <span class="text-xs text-orange-500 font-bold">القائم: <span class="masked">${formatMoney(totalDue)}</span></span>
          </div>
          <div id="supplier-debt-list" class="space-y-2 max-h-80 overflow-y-auto"></div>
        </div>
      `;

      procurementSection.appendChild(wrap);
      wrap.querySelector("#supplier-debt-form")?.addEventListener("submit", (event) => this.saveSupplierDebt(event));

      const list = wrap.querySelector("#supplier-debt-list");
      list.innerHTML = this.supplierDebts.length
        ? this.supplierDebts
            .map((d) => {
              const isOverdue = d.status !== "paid" && d.dueDate < todayISO();
              const status = d.status === "paid" ? "paid" : isOverdue ? "overdue" : "due";
              const badge =
                status === "paid"
                  ? "bg-emerald-100 text-emerald-700"
                  : status === "overdue"
                  ? "bg-red-100 text-red-700"
                  : "bg-orange-100 text-orange-700";

              return `
                <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
                  <div class="flex justify-between gap-2 items-start mb-2">
                    <div>
                      <p class="font-bold">${d.supplier}</p>
                      <p class="text-xs text-slate-400">${d.phone} | استحقاق: ${d.dueDate}</p>
                    </div>
                    <span class="text-xs px-2 py-1 rounded-full ${badge}">${debtStatusLabel(status)}</span>
                  </div>
                  <p class="font-black text-orange-500 masked mb-2">${formatMoney(d.amount)}</p>
                  ${d.notes ? `<p class="text-[11px] text-slate-500 mb-2">ملاحظة: ${d.notes}</p>` : ""}
                  <div class="flex gap-2">
                    <button onclick="app.paySupplierDebtPrompt('${d.id}')" class="text-xs px-3 py-1 rounded-lg bg-blue-500 text-white">سداد جزئي</button>
                    <button onclick="app.closeSupplierDebt('${d.id}')" class="text-xs px-3 py-1 rounded-lg bg-emerald-500 text-white">سداد كامل</button>
                  </div>
                </div>
              `;
            })
            .join("")
        : '<p class="text-xs text-slate-400">لا يوجد ديون موردين حالياً</p>';
    }

    saveSupplierDebt(event) {
      event.preventDefault();
      const formData = new FormData(event.target);
      const amount = Number(formData.get("amount") || 0);

      if (amount <= 0) {
        this.toast("مبلغ الدين غير صالح", "error");
        return;
      }

      this.supplierDebts.unshift({
        id: `sd_${Date.now()}`,
        supplier: String(formData.get("supplier") || "").trim(),
        phone: String(formData.get("phone") || "").trim(),
        amount,
        dueDate: String(formData.get("dueDate") || todayISO()),
        status: "due",
        notes: String(formData.get("notes") || "").trim()
      });

      this.save(STORAGE_KEYS.supplierDebts, this.supplierDebts);
      event.target.reset();
      this.renderSupplierDebtCenter();
      this.toast("تمت إضافة دين المورد", "success");
    }

    paySupplierDebtPrompt(debtId) {
      const debt = this.supplierDebts.find((d) => d.id === debtId);
      if (!debt || debt.status === "paid") return;

      const paidRaw = prompt(`المتبقي للمورد ${debt.supplier}: ${debt.amount.toFixed(2)}\nاكتب مبلغ السداد:`);
      if (paidRaw === null) return;
      const paid = Number(paidRaw);
      if (!Number.isFinite(paid) || paid <= 0) {
        this.toast("مبلغ غير صالح", "error");
        return;
      }

      debt.amount = Math.max(0, Number((debt.amount - paid).toFixed(2)));
      debt.status = debt.amount === 0 ? "paid" : "due";
      this.save(STORAGE_KEYS.supplierDebts, this.supplierDebts);
      this.renderSupplierDebtCenter();
      this.toast(debt.status === "paid" ? "تم إغلاق دين المورد" : "تم تسجيل سداد جزئي", "success");
    }

    closeSupplierDebt(debtId) {
      const debt = this.supplierDebts.find((d) => d.id === debtId);
      if (!debt) return;
      debt.amount = 0;
      debt.status = "paid";
      this.save(STORAGE_KEYS.supplierDebts, this.supplierDebts);
      this.renderSupplierDebtCenter();
      this.toast("تم سداد المورد بالكامل", "success");
    }

    showModal(show = true) {
      const modal = document.getElementById("modal");
      modal.classList.toggle("hidden", !show);
      modal.classList.toggle("flex", show);
      document.body.classList.toggle("modal-open", show);
    }

    checkPass() {
      const input = document.getElementById("pass-input");
      if (input.value === "123") {
        document.body.classList.add("unlocked");
        this.showModal(false);
        this.toast("تم فتح البيانات الحساسة", "success");
        input.value = "";
        return;
      }
      this.toast("كلمة المرور غير صحيحة", "error");
    }

    openAddProductModal(productId = null) {
      const modal = document.getElementById("add-product-modal");
      const content = document.getElementById("add-product-content");
      const form = document.getElementById("add-product-form");
      const title = document.getElementById("add-product-title");

      this.editingProductId = productId;

      if (productId) {
        const product = this.products.find((p) => p.id === productId);
        if (product) {
          title.textContent = "تعديل منتج";
          Object.entries(product).forEach(([key, value]) => {
            const field = form.elements.namedItem(key);
            if (field) field.value = value;
          });
        }
      } else {
        title.textContent = "إضافة منتج جديد";
        form.reset();
        const vatField = form.elements.namedItem("vat");
        if (vatField) vatField.value = 15;
      }

      modal.classList.remove("hidden");
      modal.classList.add("flex");
      requestAnimationFrame(() => {
        content.classList.remove("scale-95", "opacity-0");
      });
      document.body.classList.add("modal-open");
    }

    closeAddProductModal() {
      const modal = document.getElementById("add-product-modal");
      const content = document.getElementById("add-product-content");
      content.classList.add("scale-95", "opacity-0");
      setTimeout(() => {
        modal.classList.remove("flex");
        modal.classList.add("hidden");
      }, 200);
      document.body.classList.remove("modal-open");
      this.editingProductId = null;
    }

    saveProduct(event) {
      event.preventDefault();
      const formData = new FormData(event.target);
      const productData = Object.fromEntries(formData.entries());

      const clean = {
        id: this.editingProductId || `p${Date.now()}`,
        name: String(productData.name || "").trim(),
        gtin: String(productData.gtin || "").trim(),
        price: Number(productData.price || 0),
        cost: Number(productData.cost || 0),
        qty: Number(productData.qty || 0),
        batch: String(productData.batch || "").trim(),
        expiry: String(productData.expiry || ""),
        vat: Number(productData.vat || 15),
        manufacturer: String(productData.manufacturer || "").trim(),
        supplier: String(productData.supplier || "").trim()
      };

      if (!clean.name || !clean.gtin) {
        this.toast("بيانات المنتج غير مكتملة", "error");
        return;
      }

      if (this.editingProductId) {
        const idx = this.products.findIndex((p) => p.id === this.editingProductId);
        if (idx >= 0) this.products[idx] = clean;
      } else {
        this.products.unshift(clean);
      }

      this.save(STORAGE_KEYS.products, this.products);
      this.renderAll();
      this.closeAddProductModal();
      this.toast("تم حفظ المنتج", "success");
    }

    deleteProduct(productId) {
      this.products = this.products.filter((p) => p.id !== productId);
      this.cart = this.cart.filter((item) => item.id !== productId);
      this.save(STORAGE_KEYS.products, this.products);
      this.renderAll();
      this.toast("تم حذف المنتج", "success");
    }

    toast(message, type = "success") {
      const container = document.getElementById("toast-container");
      const node = document.createElement("div");
      node.className = `toast ${type}`;
      node.textContent = message;
      container.appendChild(node);
      requestAnimationFrame(() => node.classList.add("show"));
      setTimeout(() => {
        node.classList.remove("show");
        setTimeout(() => node.remove(), 300);
      }, 1700);
    }
  }

  window.toggleSidebar = function toggleSidebar() {
    const backdrop = document.getElementById("sidebar-backdrop");
    const isOpen = document.body.classList.toggle("sidebar-open");
    backdrop?.classList.toggle("hidden", !isOpen);
  };

  window.app = new PharmaApp();

  if (window.innerWidth >= 1024) {
    document.body.classList.add("sidebar-open");
  } else {
    document.body.classList.remove("sidebar-open");
  }
})();
