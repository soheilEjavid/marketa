import { useEffect, useState } from "react";
import { getCategories } from "../api";
import type { Category, Product } from "../types";
import { ProductFormModal } from "./ProductFormModal";

type QuickAddProductModalProps = {
  onCreated: (product: Product) => void;
  onClose: () => void;
  /** Existing products, used for live barcode/SKU duplicate checks. */
  products?: Product[];
};

export function QuickAddProductModal({
  onCreated,
  onClose,
  products,
}: QuickAddProductModalProps) {
  const [categories, setCategories] = useState<Category[]>([]);

  useEffect(() => {
    getCategories().then(setCategories).catch(() => {});
  }, []);

  return (
    <ProductFormModal
      compact
      categories={categories}
      products={products}
      onSaved={onCreated}
      onClose={onClose}
      onCategoryCreated={(category) => setCategories((current) => [...current, category])}
    />
  );
}
