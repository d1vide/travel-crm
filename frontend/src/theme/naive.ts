import type { GlobalThemeOverrides } from 'naive-ui'

/**
 * Тема Naive UI по дизайн-системе: спокойная палитра глубокого циана, плотные контролы
 * высотой 32px, радиусы 6–8px, границы 1px вместо теней. Свои стили компонентов не нужны:
 * внешний вид меняется здесь.
 */
export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#0e7490',
    primaryColorHover: '#0369a1',
    primaryColorPressed: '#155e75',
    primaryColorSuppl: '#0e7490',
    infoColor: '#0369a1',
    successColor: '#15803d',
    warningColor: '#b45309',
    errorColor: '#b91c1c',
    textColorBase: '#0f172a',
    textColor1: '#0f172a',
    textColor2: '#334155',
    textColor3: '#64748b',
    placeholderColor: '#94a3b8',
    borderColor: '#e2e8f0',
    dividerColor: '#f1f5f9',
    bodyColor: '#f8fafc',
    cardColor: '#ffffff',
    borderRadius: '6px',
    borderRadiusSmall: '4px',
    fontFamily: "'Inter Variable', Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    fontSize: '14px',
    fontSizeMedium: '14px',
    fontSizeSmall: '13px',
    heightMedium: '32px',
    heightSmall: '28px',
  },
  Button: {
    fontWeightStrong: '500',
    textColorGhost: '#475569',
    borderHover: '1px solid #cbd5e1',
  },
  Card: {
    borderRadius: '8px',
    borderColor: '#e2e8f0',
    paddingMedium: '16px',
    titleFontSizeMedium: '15px',
    titleFontWeight: '600',
  },
  DataTable: {
    thColor: '#f8fafc',
    thTextColor: '#64748b',
    thFontWeight: '600',
    tdColor: '#ffffff',
    tdColorHover: '#f8fafc',
    borderColor: '#f1f5f9',
    thPaddingMedium: '8px 12px',
    tdPaddingMedium: '10px 12px',
    fontSizeMedium: '13px',
    borderRadius: '8px',
  },
  Input: {
    border: '1px solid #e2e8f0',
    borderHover: '1px solid #cbd5e1',
    borderFocus: '1px solid #0e7490',
    boxShadowFocus: '0 0 0 1px #0e7490',
  },
  Tag: {
    borderRadius: '4px',
    heightMedium: '22px',
    fontSizeMedium: '12px',
  },
  Menu: {
    itemHeight: '36px',
    borderRadius: '6px',
    itemTextColorActive: '#0e7490',
    itemTextColorActiveHover: '#0e7490',
    itemIconColorActive: '#0e7490',
    itemIconColorActiveHover: '#0e7490',
    itemColorActive: '#ecfeff',
    itemColorActiveHover: '#ecfeff',
    groupTextColor: '#64748b',
  },
  Layout: {
    siderColor: '#ffffff',
    headerColor: '#ffffff',
    color: '#f8fafc',
    siderBorderColor: '#e2e8f0',
    headerBorderColor: '#e2e8f0',
  },
}
