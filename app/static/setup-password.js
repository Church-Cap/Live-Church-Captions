(() => {
  const form = document.querySelector('#setupPasswordForm');
  if (!form) return;

  const password = form.querySelector('#password');
  const confirmation = form.querySelector('#confirm_password');
  const lengthRequirement = form.querySelector('#passwordLengthRequirement');
  const matchRequirement = form.querySelector('#passwordMatchRequirement');
  const validationMessage = form.querySelector('#passwordValidationMessage');

  function markRequirement(element, met) {
    element.classList.toggle('is-met', met);
    element.setAttribute('data-requirement-met', String(met));
  }

  function updateRequirements() {
    const lengthMet = password.value.length >= 8;
    const matchMet = confirmation.value.length > 0 && password.value === confirmation.value;
    markRequirement(lengthRequirement, lengthMet);
    markRequirement(matchRequirement, matchMet);
    if (password.value.length > 0) password.setAttribute('aria-invalid', String(!lengthMet));
    else password.removeAttribute('aria-invalid');
    if (confirmation.value.length > 0) confirmation.setAttribute('aria-invalid', String(!matchMet));
    else confirmation.removeAttribute('aria-invalid');
    if (lengthMet && matchMet) validationMessage.hidden = true;
    return {lengthMet, matchMet};
  }

  function rejectSubmission(message, field) {
    validationMessage.textContent = message;
    validationMessage.hidden = false;
    field.setAttribute('aria-invalid', 'true');
    field.focus();
  }

  password.addEventListener('input', updateRequirements);
  confirmation.addEventListener('input', updateRequirements);
  document.querySelector('#easyOfflineInfoButton')?.addEventListener('click', () => {
    const dialog = document.querySelector('#easyOfflineInfoDialog');
    if (typeof dialog?.showModal === 'function') dialog.showModal();
    else dialog?.setAttribute('open', '');
  });
  form.addEventListener('submit', (event) => {
    const {lengthMet, matchMet} = updateRequirements();
    if (!password.value) {
      event.preventDefault();
      rejectSubmission('Enter a new operator password. It must contain at least 8 characters.', password);
    } else if (!lengthMet) {
      event.preventDefault();
      rejectSubmission('Use at least 8 characters for the operator password.', password);
    } else if (!confirmation.value) {
      event.preventDefault();
      rejectSubmission('Enter the same password again in Confirm password.', confirmation);
    } else if (!matchMet) {
      event.preventDefault();
      rejectSubmission('The passwords do not match. Re-enter the confirmation exactly.', confirmation);
    }
  });

  updateRequirements();
})();
