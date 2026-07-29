import type { ReactNode } from "react";
import { createPortal } from "react-dom";

const MODAL_ROOT_ID = "modal-root";

type ModalProps = {
  /** Called when the backdrop itself is clicked (not its content). */
  onClose: () => void;
  /** The modal's own content element (form/div), with its own className
   * for sizing (e.g. "party-form product-form") and its own
   * `onMouseDown={(e) => e.stopPropagation()}` so backdrop clicks don't
   * close it. Passed through untouched — this wrapper only owns the
   * backdrop + portal, never the content. */
  children: ReactNode;
};

/**
 * Shared centered-modal wrapper. Portals the backdrop to `#modal-root`
 * (a sibling of the app root in index.html) so `position: fixed` on it is
 * never trapped by an ancestor's containing block — the recurring bug
 * behind modals opening near a scrolled-down trigger instead of centered
 * in the viewport. Every centered modal/dialog in the app should render
 * through this rather than re-implementing its own backdrop + portal.
 */
export function Modal({ onClose, children }: ModalProps) {
  const modalContent = (
    <div className="modal-backdrop" onMouseDown={onClose}>
      {children}
    </div>
  );

  const container = document.getElementById(MODAL_ROOT_ID) ?? document.body;
  return createPortal(modalContent, container);
}
