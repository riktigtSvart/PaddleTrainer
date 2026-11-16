type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
export function controlProblem(control: Control): string {
  const label = control.getAttribute("aria-label") || [...(control.labels?.[0]?.childNodes ?? [])]
    .filter(node => node.nodeType === 3).map(node => node.textContent).join(" ").trim() || control.name || "Mező";
  const validity = control.validity;
  let reason = control.validationMessage || "Ellenőrizd a mező értékét.";
  if (validity.valueMissing) reason = "Ezt a mezőt töltsd ki.";
  else if (validity.badInput) reason = "Adj meg érvényes értéket.";
  else if (validity.rangeOverflow && "max" in control) reason = `Legfeljebb ${control.max} adható meg.`;
  else if (validity.rangeUnderflow && "min" in control) reason = `Legalább ${control.min} szükséges.`;
  else if (validity.stepMismatch) reason = "Az érték nem illeszkedik a mező megengedett lépésközéhez.";
  else if (validity.typeMismatch) reason = "Az érték formátuma nem megfelelő.";
  else if (validity.tooLong) reason = "A megadott szöveg túl hosszú.";
  return `${label}: ${reason}`;
}
export function firstFormProblem(form: HTMLFormElement) {
  const control = [...form.elements].find((element): element is Control =>
    ["INPUT", "SELECT", "TEXTAREA"].includes(element.tagName) && (element as Control).willValidate && !(element as Control).validity.valid);
  return control ? { control, text: controlProblem(control) } : null;
}
export function revealInvalid(control: Control) {
  let parent = control.closest("details");
  while (parent) { parent.open = true; parent = parent.parentElement?.closest("details") ?? null; }
  control.scrollIntoView?.({ block: "nearest" });
  control.focus({ preventScroll: true });
}
