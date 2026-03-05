import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://54.81.253.69:8000'

export const maxDuration = 60

async function handler(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/')
  const url = `${BACKEND_URL}/${path}${request.nextUrl.search}`

  let body = undefined
  let contentType = request.headers.get('content-type') || ''

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    if (contentType.includes('multipart/form-data')) {
      body = await request.formData()
    } else {
      body = await request.text()
    }
  }

  const headers: Record<string, string> = {}
  if (contentType && !contentType.includes('multipart/form-data')) {
    headers['Content-Type'] = contentType
  }

  const response = await fetch(url, {
    method: request.method,
    body: body as any,
    headers,
  })

  const responseContentType = response.headers.get('content-type') || ''

  if (responseContentType.includes('application/pdf') || responseContentType.includes('octet-stream')) {
    const buffer = await response.arrayBuffer()
    return new NextResponse(buffer, {
      status: response.status,
      headers: {
        'Content-Type': responseContentType,
        'Content-Disposition': response.headers.get('Content-Disposition') || 'attachment',
      },
    })
  }

  const data = await response.json()
  return NextResponse.json(data, { status: response.status })
}

export const GET = handler
export const POST = handler