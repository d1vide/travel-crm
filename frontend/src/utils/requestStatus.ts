import type { RequestStatus } from '@/api/requests'

export const requestStatuses: Record<RequestStatus, string> = {
  new: 'Новая',
  in_progress: 'В работе',
  offer_prepared: 'Предложение готово',
  booked: 'Забронирована',
  completed: 'Завершена',
  cancelled: 'Отменена',
}
