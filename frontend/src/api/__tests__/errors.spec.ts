import { describe, expect, it } from 'vitest'
import { ApiError, apiErrorFromNetwork, apiErrorFromResponse } from '../errors'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiErrorFromResponse', () => {
  it('берёт код, сообщение и ошибки полей из тела ответа сервера', async () => {
    const response = jsonResponse(422, {
      code: 'validation_error',
      message: 'Проверьте заполнение формы',
      fields: [{ field: 'phone', message: 'Укажите телефон или email' }],
    })

    const error = await apiErrorFromResponse(response)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(422)
    expect(error.code).toBe('validation_error')
    expect(error.message).toBe('Проверьте заполнение формы')
    expect(error.fields).toEqual([{ field: 'phone', message: 'Укажите телефон или email' }])
  })

  it('использует русское сообщение по статусу, если тело пустое', async () => {
    const unauthorized = await apiErrorFromResponse(new Response(null, { status: 401 }))
    const forbidden = await apiErrorFromResponse(new Response(null, { status: 403 }))
    const server = await apiErrorFromResponse(new Response(null, { status: 503 }))

    expect(unauthorized.code).toBe('unauthorized')
    expect(unauthorized.message).toBe('Требуется вход в систему')
    expect(forbidden.code).toBe('forbidden')
    expect(forbidden.message).toBe('Недостаточно прав для этого действия')
    expect(server.code).toBe('server_error')
    expect(server.message).toBe('Ошибка сервера, попробуйте позже')
  })

  it('не падает на теле, которое не является JSON', async () => {
    const response = new Response('<html>Bad gateway</html>', { status: 502 })

    const error = await apiErrorFromResponse(response)

    expect(error.code).toBe('server_error')
    expect(error.fields).toEqual([])
  })

  it('отбрасывает некорректные элементы списка полей', async () => {
    const response = jsonResponse(422, {
      code: 'validation_error',
      message: 'Ошибка',
      fields: [
        { field: 'budget', message: 'Бюджет не может быть отрицательным' },
        'мусор',
        { field: 1 },
      ],
    })

    const error = await apiErrorFromResponse(response)

    expect(error.fields).toEqual([
      { field: 'budget', message: 'Бюджет не может быть отрицательным' },
    ])
  })
})

describe('apiErrorFromNetwork', () => {
  it('описывает недоступность сервера понятным сообщением', () => {
    const error = apiErrorFromNetwork(new TypeError('Failed to fetch'))

    expect(error.status).toBe(0)
    expect(error.code).toBe('network_error')
    expect(error.message).toBe('Нет связи с сервером, проверьте подключение')
  })
})
