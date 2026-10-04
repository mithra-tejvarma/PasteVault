/**
 * PasteVault - Vanilla JavaScript helper for clipboard copy,
 * character counting, and interactive UX enhancements.
 */

document.addEventListener('DOMContentLoaded', () => {
  initClipboardFeatures();
  initFormCounters();
  initTextareaTabSupport();
});

/**
 * Initializes clipboard copying for both Paste Content and Share URL.
 */
function initClipboardFeatures() {
  const btnCopyContent = document.getElementById('btn-copy-content');
  const btnCopyUrl = document.getElementById('btn-copy-url');
  const copiedToast = document.getElementById('copied-toast');

  function showToast(customMessage) {
    if (!copiedToast) return;
    copiedToast.textContent = customMessage || 'Copied!';
    copiedToast.classList.add('visible');
    setTimeout(() => {
      copiedToast.classList.remove('visible');
    }, 2000);
  }

  // Helper to copy text with modern Clipboard API and legacy fallback
  function copyTextToClipboard(text, onSuccess, onFail) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text)
        .then(onSuccess)
        .catch(err => {
          console.warn('Clipboard API error, trying fallback:', err);
          fallbackCopy(text, onSuccess, onFail);
        });
    } else {
      fallbackCopy(text, onSuccess, onFail);
    }
  }

  function fallbackCopy(text, onSuccess, onFail) {
    try {
      const tempTextArea = document.createElement('textarea');
      tempTextArea.value = text;
      tempTextArea.style.position = 'fixed';
      tempTextArea.style.left = '-9999px';
      tempTextArea.style.top = '0';
      document.body.appendChild(tempTextArea);
      tempTextArea.focus();
      tempTextArea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(tempTextArea);
      if (successful && onSuccess) onSuccess();
      else if (!successful && onFail) onFail();
    } catch (e) {
      if (onFail) onFail(e);
    }
  }

  // 1. Copy Paste Content
  if (btnCopyContent) {
    btnCopyContent.addEventListener('click', () => {
      const codeElement = document.querySelector('#paste-content-display code');
      if (!codeElement) return;

      const content = codeElement.textContent;
      const originalText = btnCopyContent.querySelector('.btn-text').textContent;

      copyTextToClipboard(content, () => {
        btnCopyContent.querySelector('.btn-text').textContent = 'Copied!';
        btnCopyContent.classList.add('btn-primary');
        btnCopyContent.classList.remove('btn-secondary');
        showToast('Content Copied!');

        setTimeout(() => {
          btnCopyContent.querySelector('.btn-text').textContent = originalText;
          btnCopyContent.classList.remove('btn-primary');
          btnCopyContent.classList.add('btn-secondary');
        }, 2000);
      }, () => {
        alert('Could not copy to clipboard. Please copy manually.');
      });
    });
  }

  // 2. Copy Share URL
  if (btnCopyUrl) {
    btnCopyUrl.addEventListener('click', () => {
      const url = window.location.href;
      const originalText = btnCopyUrl.querySelector('.btn-text').textContent;

      copyTextToClipboard(url, () => {
        btnCopyUrl.querySelector('.btn-text').textContent = 'Copied!';
        btnCopyUrl.classList.add('btn-primary');
        btnCopyUrl.classList.remove('btn-secondary');
        showToast('Link Copied!');

        setTimeout(() => {
          btnCopyUrl.querySelector('.btn-text').textContent = originalText;
          btnCopyUrl.classList.remove('btn-primary');
          btnCopyUrl.classList.add('btn-secondary');
        }, 2000);
      }, () => {
        alert('Could not copy URL. Please copy manually from the address bar.');
      });
    });
  }
}

/**
 * Initializes character count indicators on create paste form.
 */
function initFormCounters() {
  const titleInput = document.getElementById('title');
  const titleCounter = document.getElementById('title-counter');
  const contentInput = document.getElementById('content');
  const contentCounter = document.getElementById('content-counter');

  if (titleInput && titleCounter) {
    const updateTitleCount = () => {
      titleCounter.textContent = `${titleInput.value.length} / 100`;
    };
    titleInput.addEventListener('input', updateTitleCount);
    updateTitleCount(); // initial state
  }

  if (contentInput && contentCounter) {
    const updateContentCount = () => {
      const len = contentInput.value.length;
      contentCounter.textContent = `${len.toLocaleString()} / 50,000`;
    };
    contentInput.addEventListener('input', updateContentCount);
    updateContentCount(); // initial state
  }
}

/**
 * Allows pressing TAB inside the code editor textarea to insert 4 spaces
 * instead of shifting keyboard focus away.
 */
function initTextareaTabSupport() {
  const textarea = document.querySelector('.code-editor');
  if (!textarea) return;

  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const tabSpaces = '    '; // 4 spaces

      textarea.value = textarea.value.substring(0, start) + tabSpaces + textarea.value.substring(end);
      textarea.selectionStart = textarea.selectionEnd = start + tabSpaces.length;

      // Trigger input event to update char counter
      textarea.dispatchEvent(new Event('input'));
    }
  });
}
