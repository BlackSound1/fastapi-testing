/**
 * If the `error` detail is a string, return that.
 * If it's an array, return each error message joined by a '.'.
 * Else return generic error.
 * @param error
 * @returns Error messages.
 */
export function getErrorMessage(error) {
  if (typeof error.detail === "string") {
    return error.detail;
  } else if (Array.isArray(error.detail)) {
    return error.detail.map((err) => err.msg).join(". ");
  }
  return "An error occurred. Please try again.";
}

/**
 * Shows a modal given a `modalID`.
 * @param modalID The ID of the modal to show.
 * @returns The modal, given the `modalID`.
 */
export function showModal(modalId) {
  const modal = bootstrap.Modal.getOrCreateInstance(
    document.getElementById(modalId),
  );
  modal.show();
  return modal;
}

/**
 * Hide a modal by `modalID`.
 * @param {*} modalID The ID of the modal to hide.
 */
export function hideModal(modalId) {
  const modal = bootstrap.Modal.getInstance(document.getElementById(modalId));
  if (modal) modal.hide();
}
