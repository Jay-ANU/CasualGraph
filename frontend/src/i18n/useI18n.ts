import { useContext } from 'react';
import { LocaleContext } from './context';
export const useI18n = () => useContext(LocaleContext);
