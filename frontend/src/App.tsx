import { useEffect, useState } from "react";

import { getCurrentUser } from "./api";
import { Sidebar, type Page } from "./components/Sidebar";
import { useI18n } from "./i18n";
import { PurchaseDetailView } from "./components/PurchaseDetailView";
import { Checks } from "./pages/Checks";
import { CustomerDetail } from "./pages/CustomerDetail";
import { Customers } from "./pages/Customers";
import { Dashboard } from "./pages/Dashboard";
import { InventoryHistory } from "./pages/InventoryHistory";
import { Login } from "./pages/Login";
import { LoyaltyClub } from "./pages/LoyaltyClub";
import { Products } from "./pages/Products";
import { Purchases } from "./pages/Purchases";
import { Reports } from "./pages/Reports";
import { Sales } from "./pages/Sales";
import { SupplierDetail } from "./pages/SupplierDetail";
import { Suppliers } from "./pages/Suppliers";
import { Users } from "./pages/Users";
import { clearSession, getSession, onUnauthorized, type Session } from "./session";

type View =
  | { page: Page }
  | { page: "customer-detail"; customerId: number; customerName: string }
  | { page: "supplier-detail"; supplierId: number; supplierName: string }
  | { page: "purchase-detail"; purchaseId: number; from: "checks" };

export default function App() {
  const { t } = useI18n();
  const [view, setView] = useState<View>({ page: "dashboard" });
  const [session, setSession] = useState<Session | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

  useEffect(() => {
    const stored = getSession();
    if (!stored) {
      setAuthChecking(false);
      return;
    }
    // Validate against the real backend rather than trusting localStorage
    // blindly — GET /auth/me confirms the token still works and refreshes
    // role/full_name in case an admin changed them since last login.
    getCurrentUser()
      .then((me) => {
        setSession({ ...stored, username: me.username, fullName: me.full_name, role: me.role });
      })
      .catch(() => {
        clearSession();
        setSession(null);
      })
      .finally(() => setAuthChecking(false));
  }, []);

  useEffect(() => onUnauthorized(() => setSession(null)), []);

  function handleLogout() {
    clearSession();
    setSession(null);
    setView({ page: "dashboard" });
  }

  if (authChecking) {
    return (
      <div className="app-shell">
        <div className="empty-state">{t("loading")}</div>
      </div>
    );
  }

  if (!session) {
    return <Login onLoginSuccess={setSession} />;
  }

  const content = (() => {
    switch (view.page) {
      case "dashboard":
        return <Dashboard onNavigate={(page) => setView({ page })} />;
      case "sales":
        return <Sales />;
      case "purchases":
        return <Purchases />;
      case "products":
        return <Products />;
      case "customers":
        return (
          <Customers
            onViewLedger={(customerId, customerName) =>
              setView({ page: "customer-detail", customerId, customerName })
            }
          />
        );
      case "suppliers":
        return (
          <Suppliers
            onViewLedger={(supplierId, supplierName) =>
              setView({ page: "supplier-detail", supplierId, supplierName })
            }
          />
        );
      case "loyalty-club":
        return <LoyaltyClub />;
      case "inventory":
        return <InventoryHistory />;
      case "users":
        return <Users />;
      case "customer-detail":
        return (
          <CustomerDetail
            customerId={view.customerId}
            customerName={view.customerName}
            onBack={() => setView({ page: "customers" })}
          />
        );
      case "reports":
        return <Reports onNavigate={(page) => setView({ page })} />;
      case "supplier-detail":
        return (
          <SupplierDetail
            supplierId={view.supplierId}
            supplierName={view.supplierName}
            onBack={() => setView({ page: "suppliers" })}
          />
        );
      case "checks":
        return (
          <Checks
            onViewPurchase={(purchaseId) => setView({ page: "purchase-detail", purchaseId, from: "checks" })}
          />
        );
      case "purchase-detail":
        return (
          <PurchaseDetailView
            purchaseId={view.purchaseId}
            onBack={() => setView({ page: view.from })}
          />
        );
    }
  })();

  const activePage: Page =
    view.page === "customer-detail" || view.page === "supplier-detail" || view.page === "purchase-detail"
      ? view.page === "customer-detail"
        ? "customers"
        : view.page === "supplier-detail"
          ? "suppliers"
          : "checks"
      : view.page;

  return (
    <div className="app-shell">
      <Sidebar
        activePage={activePage}
        onNavigate={(page) => setView({ page })}
        session={session}
        onLogout={handleLogout}
      />
      <div className="page-transition" key={view.page}>
        {content}
      </div>
    </div>
  );
}