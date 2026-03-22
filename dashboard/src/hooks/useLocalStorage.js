import { useState, useEffect, useCallback } from 'react';

/**
 * Custom hook for persistent state with localStorage
 * @param {string} key - localStorage key
 * @param {*} defaultValue - Default value if no stored value
 * @param {Object} options - Options object
 * @param {boolean} options.isSecure - If true, don't save to localStorage (for sensitive data)
 * @param {Function} options.serialize - Custom serialize function
 * @param {Function} options.deserialize - Custom deserialize function
 */
export function useLocalStorage(key, defaultValue, options = {}) {
  const { 
    isSecure = false,
    serialize = JSON.stringify,
    deserialize = JSON.parse 
  } = options;

  const [value, setValue] = useState(() => {
    if (isSecure) return defaultValue;
    
    try {
      const stored = localStorage.getItem(key);
      if (stored === null) return defaultValue;
      return deserialize(stored);
    } catch (err) {
      console.warn(`Error reading localStorage key "${key}":`, err);
      return defaultValue;
    }
  });

  useEffect(() => {
    if (isSecure) return;
    
    try {
      localStorage.setItem(key, serialize(value));
    } catch (err) {
      console.warn(`Error setting localStorage key "${key}":`, err);
    }
  }, [key, value, serialize, isSecure]);

  const removeValue = useCallback(() => {
    try {
      localStorage.removeItem(key);
      setValue(defaultValue);
    } catch (err) {
      console.warn(`Error removing localStorage key "${key}":`, err);
    }
  }, [key, defaultValue]);

  return [value, setValue, removeValue];
}

export default useLocalStorage;
