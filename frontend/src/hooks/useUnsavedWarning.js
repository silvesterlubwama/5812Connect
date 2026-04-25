import { useEffect, useRef, useCallback } from 'react';

/**
 * Hook to warn users about unsaved changes when navigating away.
 * @param {boolean} isDirty - Whether the form has unsaved changes
 * @param {string} message - Warning message to display
 */
export function useUnsavedWarning(isDirty, message = 'You have unsaved changes. Leave anyway?') {
  const isDirtyRef = useRef(isDirty);
  isDirtyRef.current = isDirty;

  useEffect(() => {
    const handler = (e) => {
      if (!isDirtyRef.current) return;
      e.preventDefault();
      e.returnValue = message;
      return message;
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [message]);
}

/**
 * Track form dirty state by comparing current form to initial values.
 */
export function useFormDirty(currentForm, initialForm) {
  return JSON.stringify(currentForm) !== JSON.stringify(initialForm);
}
