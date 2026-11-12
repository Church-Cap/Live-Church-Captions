(() => {
  const form = document.querySelector('#setupPasswordForm');
  const card = document.querySelector('.onboarding-card');
  if (!form || !card) return;

  const steps = [...form.querySelectorAll('[data-onboarding-step]')];
  const indicators = [...form.querySelectorAll('[data-step-indicator]')];
  const backButton = form.querySelector('#onboardingBack');
  const nextButton = form.querySelector('#onboardingNext');
  const submitButton = form.querySelector('#saveOperatorPassword');
  const progress = form.querySelector('.onboarding-progress-track');
  const progressBar = form.querySelector('#onboardingProgressBar');
  const progressPercent = form.querySelector('#onboardingProgressPercent');
  const password = form.querySelector('#password');
  const confirmation = form.querySelector('#confirm_password');
  const lengthRequirement = form.querySelector('#passwordLengthRequirement');
  const matchRequirement = form.querySelector('#passwordMatchRequirement');
  const validationMessage = form.querySelector('#passwordValidationMessage');
  const audioInput = form.querySelector('#setupAudioDevice');
  const translatedSetup = form.querySelector('#translatedLanguageSetup');
  const activeLanguageLimit = form.querySelector('#translationMaxActiveLanguages');
  const activeLanguageLimitValue = form.querySelector('#translationMaxActiveLanguagesValue');
  const languagePackInputs = [...form.querySelectorAll('input[name="language_packs"]')];
  const selectAllLanguagePacks = form.querySelector('#selectAllLanguagePacks');
  const spokenStepIndicator = form.querySelector('[data-spoken-step]');
  const spokenAudioChoices = [...form.querySelectorAll('input[name="spoken_audio_setup"]')];
  const spokenAudioOptions = form.querySelector('#spokenAudioOptions');
  const spokenAudioPackages = [...form.querySelectorAll('input[name="spoken_audio_packages"]')];
  const selectAllSpokenAudio = form.querySelector('#selectAllSpokenAudio');
  const spokenAudioValidation = form.querySelector('#spokenAudioValidationMessage');
  const heroTitle = document.querySelector('#onboardingHeroTitle');
  const heroCopy = document.querySelector('#onboardingHeroCopy');
  const heroSteps = [
    ['Set up clear captions.', 'A guided setup for secure controls, suitable performance and the right language coverage for your church.'],
    ['Keep controls in trusted hands.', 'Choose a strong operator password and decide which trusted devices can reach Church Cap controls.'],
    ['Connect the service sound.', 'Choose the microphone, mixer or audio interface Church Cap should listen to. You can change it later.'],
    ['Use settings suited to this computer.', 'Church Cap checks local processor and acceleration information, then suggests a safe starting point.'],
    ['Choose simple language coverage.', 'Choose one or more local packs without configuring a long language list. Automatic mode becomes available when both packs are selected.'],
    ['Add listening only if it helps.', 'Spoken translated audio is optional. Choose the voices your visitors need, or skip it and keep translated captions only.'],
    ['Ready for a proper sound test.', 'Review the choices, finish setup, then test with the same microphone or sound-desk feed used in a service.'],
  ];
  let currentStep = 1;
  let submitting = false;
  let transitioning = false;

  function markRequirement(element, met) {
    if (!element) return;
    element.classList.toggle('is-met', met);
    element.setAttribute('data-requirement-met', String(met));
  }

  function updatePasswordRequirements() {
    const lengthMet = (password?.value || '').length >= 8;
    const matchMet = (confirmation?.value || '').length > 0 && password.value === confirmation.value;
    markRequirement(lengthRequirement, lengthMet);
    markRequirement(matchRequirement, matchMet);
    if (password?.value.length) password.setAttribute('aria-invalid', String(!lengthMet));
    else password?.removeAttribute('aria-invalid');
    if (confirmation?.value.length) confirmation.setAttribute('aria-invalid', String(!matchMet));
    else confirmation?.removeAttribute('aria-invalid');
    if (lengthMet && matchMet && validationMessage) validationMessage.hidden = true;
    return {lengthMet, matchMet};
  }

  function rejectPassword(message, field) {
    if (validationMessage) {
      validationMessage.textContent = message;
      validationMessage.hidden = false;
    }
    field?.setAttribute('aria-invalid', 'true');
    field?.focus();
    return false;
  }

  function validateSecurity() {
    const {lengthMet, matchMet} = updatePasswordRequirements();
    if (!password?.value) return rejectPassword('Enter a new operator password. It must contain at least 8 characters.', password);
    if (!lengthMet) return rejectPassword('Use at least 8 characters for the operator password.', password);
    if (!confirmation?.value) return rejectPassword('Enter the same password again in Confirm password.', confirmation);
    if (!matchMet) return rejectPassword('The passwords do not match. Re-enter the confirmation exactly.', confirmation);
    return true;
  }

  function selectedPackInputs() {
    return languagePackInputs.filter((input) => input.checked);
  }

  function translatedPackSelected() {
    return selectedPackInputs().some((input) => input.value !== 'english');
  }

  function updateActiveLanguageLimit() {
    if (!activeLanguageLimit || !activeLanguageLimitValue) return;
    const value = Math.max(1, Number(activeLanguageLimit.value || 1));
    const minimum = Number(activeLanguageLimit.min || 1);
    const maximum = Math.max(minimum + 1, Number(activeLanguageLimit.max || 20));
    const progress = ((value - minimum) / (maximum - minimum)) * 100;
    activeLanguageLimit.style.setProperty('--range-progress', `${Math.max(0, Math.min(100, progress))}%`);
    activeLanguageLimitValue.value = String(value);
    activeLanguageLimitValue.textContent = `${value} ${value === 1 ? 'language' : 'languages'}`;
  }

  function activeStepNumbers() {
    return translatedPackSelected() ? [1, 2, 3, 4, 5, 6, 7] : [1, 2, 3, 4, 5, 7];
  }

  function updateNextButtonLabel() {
    if (!nextButton) return;
    nextButton.textContent = currentStep === 1
      ? 'Get started'
      : (currentStep === 5 && translatedPackSelected()
        ? 'Continue to spoken audio'
        : (currentStep === 6 ? 'Continue to review' : 'Continue'));
  }

  function updateVisibleStepIndicators() {
    const active = activeStepNumbers();
    if (spokenStepIndicator) {
      const available = active.includes(6);
      spokenStepIndicator.hidden = !available;
      spokenStepIndicator.classList.toggle('is-available', available);
      spokenStepIndicator.setAttribute('aria-hidden', String(!available));
    }
    indicators.forEach((indicator) => {
      const step = Number(indicator.dataset.stepIndicator);
      if (step === 6) indicator.hidden = !active.includes(6);
      const number = indicator.querySelector('span');
      if (number && number.textContent !== '✓') {
        number.textContent = step === 1 ? '•' : String(step - 1);
      }
    });
    form.querySelector('.onboarding-step-indicators')?.style.setProperty('--onboarding-step-count', String(active.length));
  }

  function normalisePackSelection(changedInput = null) {
    const english = languagePackInputs.find((input) => input.value === 'english');
    const translated = languagePackInputs.filter((input) => input.value !== 'english' && !input.disabled);
    if (changedInput?.value === 'english' && changedInput.checked) {
      translated.forEach((input) => { input.checked = false; });
    } else if (changedInput?.value !== 'english' && changedInput?.checked && english) {
      english.checked = false;
    }
    if (!languagePackInputs.some((input) => input.checked) && english) english.checked = true;
  }

  function updatePackSelection(changedInput = null) {
    normalisePackSelection(changedInput);
    form.querySelectorAll('.onboarding-pack-card').forEach((option) => {
      const input = option.querySelector('input[name="language_packs"]');
      option.classList.toggle('is-selected', Boolean(input?.checked));
    });
    const translated = languagePackInputs.filter((input) => input.value !== 'english' && !input.disabled);
    const allSelected = translated.length > 1 && translated.every((input) => input.checked);
    if (selectAllLanguagePacks) {
      selectAllLanguagePacks.disabled = allSelected || translated.length < 2;
      selectAllLanguagePacks.textContent = allSelected ? 'All packs selected' : 'Select all packs';
    }
    if (translatedSetup) translatedSetup.hidden = !translatedPackSelected();
    updateVisibleStepIndicators();
    updateNextButtonLabel();
  }

  function spokenAudioWillInstall() {
    return form.querySelector('input[name="spoken_audio_setup"]:checked')?.value === 'install';
  }

  function selectedSpokenAudioPackages() {
    return spokenAudioPackages.filter((input) => input.checked);
  }

  function updateSpokenAudioSelection() {
    const installing = spokenAudioWillInstall();
    if (spokenAudioOptions) spokenAudioOptions.hidden = !installing;
    spokenAudioPackages.forEach((input) => {
      input.closest('.onboarding-voice-card')?.classList.toggle('is-selected', input.checked);
    });
    const allSelected = spokenAudioPackages.length > 0 && spokenAudioPackages.every((input) => input.checked);
    if (selectAllSpokenAudio) {
      selectAllSpokenAudio.disabled = installing && allSelected;
      selectAllSpokenAudio.textContent = allSelected ? 'All voices selected' : 'Select all voices';
    }
    if (spokenAudioValidation && (!installing || selectedSpokenAudioPackages().length)) spokenAudioValidation.hidden = true;
  }

  function validateSpokenAudio() {
    if (!spokenAudioWillInstall() || selectedSpokenAudioPackages().length) return true;
    if (spokenAudioValidation) {
      spokenAudioValidation.textContent = 'Choose at least one spoken language, or select Skip for now.';
      spokenAudioValidation.hidden = false;
    }
    spokenAudioPackages[0]?.focus();
    return false;
  }

  function updateReview() {
    const security = form.querySelector('input[name="security_mode"]:checked')?.value;
    const securityCopy = {
      secure_operator: 'Only this computer',
      easy_offline: 'Trusted devices on this network',
      managed_https: 'Managed church devices',
    };
    const reviewSecurity = form.querySelector('#reviewSecurity');
    if (reviewSecurity) reviewSecurity.textContent = securityCopy[security] || 'Only this computer';

    const reviewAudioInput = form.querySelector('#reviewAudioInput');
    if (reviewAudioInput && audioInput) {
      const selectedOption = audioInput.options[audioInput.selectedIndex];
      reviewAudioInput.textContent = selectedOption?.dataset.reviewLabel
        || selectedOption?.textContent?.trim()
        || 'System default input';
    }

    const reviewPerformance = form.querySelector('#reviewPerformance');
    if (reviewPerformance) {
      reviewPerformance.textContent = form.querySelector('input[name="performance_setup"]:checked')?.value === 'later'
        ? 'Keep current settings; decide later'
        : card.dataset.recommendedPerformance;
    }

    const translatedPacks = selectedPackInputs().filter((input) => input.value !== 'english');
    const packLabels = translatedPacks.map((input) => input.closest('.onboarding-pack-card')?.dataset.packLabel).filter(Boolean);
    const packLabel = packLabels.length > 1 ? 'Broad + PyTorch SMaLL-100 · Automatic' : (packLabels[0] || 'English captions only');
    const reviewLanguages = form.querySelector('#reviewLanguages');
    const reviewLimitRow = form.querySelector('#reviewLanguageLimitRow');
    const reviewLimit = form.querySelector('#reviewLanguageLimit');
    const reviewSpokenAudioRow = form.querySelector('#reviewSpokenAudioRow');
    const reviewSpokenAudio = form.querySelector('#reviewSpokenAudio');
    const installNotice = form.querySelector('#reviewInstallNotice');
    if (reviewLanguages) reviewLanguages.textContent = packLabel;
    if (translatedPackSelected()) {
      if (reviewLimitRow) reviewLimitRow.hidden = false;
      if (reviewLimit) reviewLimit.textContent = String(Math.max(1, Number(form.querySelector('#translationMaxActiveLanguages')?.value || 1)));
      if (reviewSpokenAudioRow) reviewSpokenAudioRow.hidden = false;
      const selectedVoices = selectedSpokenAudioPackages();
      if (reviewSpokenAudio) {
        reviewSpokenAudio.textContent = spokenAudioWillInstall()
          ? `${selectedVoices.length} voice pack${selectedVoices.length === 1 ? '' : 's'} selected`
          : 'Skip for now';
      }
      if (installNotice) installNotice.textContent = packLabels.length > 1
        ? 'Both language packs will install one at a time after setup. Automatic mode will prefer the efficient local provider, and English captions remain available throughout.'
        : `${packLabel} will download after setup. English captions remain available while the local installation finishes.`;
      if (installNotice) installNotice.textContent += ' Once installed, visitors can choose any language in the pack; use Restricted mode on the Operator Languages page to limit the list.';
      if (installNotice && spokenAudioWillInstall()) installNotice.textContent += ' Spoken-audio voices will install afterwards.';
    } else {
      if (reviewLimitRow) reviewLimitRow.hidden = true;
      if (reviewSpokenAudioRow) reviewSpokenAudioRow.hidden = true;
      if (installNotice) installNotice.textContent = 'Setup will save the password and settings. No language download will start.';
    }
  }

  function validateStep(step) {
    if (step === 2) return validateSecurity();
    if (step === 6) return validateSpokenAudio();
    return true;
  }

  async function showStep(step, {focus = true} = {}) {
    const activeNumbers = activeStepNumbers();
    const nextStep = activeNumbers.includes(step) ? step : activeNumbers[activeNumbers.length - 1];
    const previousStep = currentStep;
    const outgoing = steps.find((panel) => !panel.hidden);
    const direction = nextStep >= previousStep ? 1 : -1;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (focus && outgoing && nextStep !== previousStep && !reduceMotion && typeof outgoing.animate === 'function') {
      transitioning = true;
      let outgoingAnimation = null;
      try {
        outgoingAnimation = outgoing.animate(
          [
            {opacity: 1, transform: 'translateX(0)'},
            {opacity: 0, transform: `translateX(${-direction * 10}px)`},
          ],
          {duration: 120, easing: 'ease-in', fill: 'forwards'},
        );
        await outgoingAnimation.finished;
      } catch (_) {}
      outgoingAnimation?.cancel();
    }
    currentStep = nextStep;
    steps.forEach((panel) => {
      panel.hidden = Number(panel.dataset.onboardingStep) !== currentStep;
    });
    const currentIndex = activeNumbers.indexOf(currentStep);
    indicators.forEach((indicator) => {
      const number = Number(indicator.dataset.stepIndicator);
      indicator.toggleAttribute('aria-current', number === currentStep);
      const indicatorIndex = activeNumbers.indexOf(number);
      indicator.classList.toggle('is-complete', indicatorIndex >= 0 && indicatorIndex < currentIndex);
    });
    const taskNumbers = activeNumbers.filter((number) => number !== 1);
    const taskIndex = taskNumbers.indexOf(currentStep);
    const percent = currentStep === 1 ? 0 : Math.round(((taskIndex + 1) / taskNumbers.length) * 100);
    progress?.setAttribute('aria-valuenow', String(percent));
    progressBar?.style.setProperty('--onboarding-progress', `${percent}%`);
    if (progressPercent) progressPercent.textContent = `${percent}%`;
    if (backButton) backButton.hidden = currentIndex === 0;
    if (nextButton) {
      nextButton.hidden = currentIndex === activeNumbers.length - 1;
      updateNextButtonLabel();
    }
    if (submitButton) submitButton.hidden = currentIndex !== activeNumbers.length - 1;
    if (currentIndex === activeNumbers.length - 1) updateReview();
    const hero = heroSteps[currentStep - 1];
    if (heroTitle) heroTitle.textContent = hero[0];
    if (heroCopy) heroCopy.textContent = hero[1];
    const activeStep = steps.find((panel) => !panel.hidden);
    if (activeStep) activeStep.scrollTop = 0;
    if (focus && activeStep && nextStep !== previousStep && !reduceMotion && typeof activeStep.animate === 'function') {
      activeStep.animate(
        [
          {opacity: 0, transform: `translateX(${direction * 12}px)`},
          {opacity: 1, transform: 'translateX(0)'},
        ],
        {duration: 190, easing: 'cubic-bezier(.2,.8,.2,1)'},
      );
    }
    if (focus) activeStep?.querySelector('h1')?.focus({preventScroll: true});
    if (window.matchMedia?.('(max-width: 780px)').matches && currentStep > 1) {
      window.scrollTo({top: 0, behavior: 'auto'});
    } else {
      card.scrollTo({top: 0, behavior: 'auto'});
    }
    transitioning = false;
  }

  nextButton?.addEventListener('click', () => {
    if (!transitioning && validateStep(currentStep)) {
      const active = activeStepNumbers();
      void showStep(active[Math.min(active.length - 1, active.indexOf(currentStep) + 1)]);
    }
  });
  backButton?.addEventListener('click', () => {
    if (!transitioning) {
      const active = activeStepNumbers();
      void showStep(active[Math.max(0, active.indexOf(currentStep) - 1)]);
    }
  });
  password?.addEventListener('input', updatePasswordRequirements);
  confirmation?.addEventListener('input', updatePasswordRequirements);
  languagePackInputs.forEach((input) => input.addEventListener('change', () => updatePackSelection(input)));
  activeLanguageLimit?.addEventListener('input', updateActiveLanguageLimit);
  selectAllLanguagePacks?.addEventListener('click', () => {
    languagePackInputs.forEach((input) => { input.checked = input.value !== 'english' && !input.disabled; });
    form.querySelector('#languagePackCompatibility')?.closest('details')?.setAttribute('open', '');
    updatePackSelection();
  });
  spokenAudioChoices.forEach((input) => input.addEventListener('change', updateSpokenAudioSelection));
  spokenAudioPackages.forEach((input) => input.addEventListener('change', updateSpokenAudioSelection));
  selectAllSpokenAudio?.addEventListener('click', () => {
    spokenAudioPackages.forEach((input) => { input.checked = true; });
    updateSpokenAudioSelection();
  });

  const easyOfflineInfoButton = document.querySelector('#easyOfflineInfoButton');
  const easyOfflineInfoDialog = document.querySelector('#easyOfflineInfoDialog');
  easyOfflineInfoButton?.addEventListener('click', () => {
    if (typeof easyOfflineInfoDialog?.showModal === 'function') easyOfflineInfoDialog.showModal();
    else easyOfflineInfoDialog?.setAttribute('open', '');
  });

  const languagePackInfoButton = document.querySelector('#languagePackInfoButton');
  const languagePackInfoDialog = document.querySelector('#languagePackInfoDialog');
  languagePackInfoButton?.addEventListener('click', () => {
    if (typeof languagePackInfoDialog?.showModal === 'function') languagePackInfoDialog.showModal();
    else languagePackInfoDialog?.setAttribute('open', '');
  });

  form.addEventListener('submit', (event) => {
    if (submitting) return;
    if (!validateSecurity()) {
      event.preventDefault();
      showStep(2, {focus: false});
      return;
    }
    submitting = true;
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = translatedPackSelected() ? 'Saving and starting downloads…' : 'Saving setup…';
    }
    if (backButton) backButton.disabled = true;
  });

  updatePasswordRequirements();
  updateActiveLanguageLimit();
  updatePackSelection();
  updateSpokenAudioSelection();
  const serverError = form.querySelector('.onboarding-error')?.textContent || '';
  const errorStep = /spoken|voice/i.test(serverError)
    ? 6
    : (/microphone|audio input|interface|sound input/i.test(serverError)
      ? 3
      : (/language|translation|pack/i.test(serverError) ? 5 : (/password/i.test(serverError) ? 2 : 1)));
  showStep(errorStep, {focus: false});
})();
