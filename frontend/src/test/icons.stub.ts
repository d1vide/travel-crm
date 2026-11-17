import { h } from 'vue'

// Лёгкая замена иконок для тестов: пакет иконок велик и медленно загружается в jsdom.
const Icon = { render: () => h('svg') }

export const AirplaneOutline = Icon
export const BarChartOutline = Icon
export const CompassOutline = Icon
export const DocumentTextOutline = Icon
export const LogOutOutline = Icon
export const PeopleOutline = Icon
export const PersonAddOutline = Icon
export const SearchOutline = Icon
export const SpeedometerOutline = Icon
export const WalletOutline = Icon
