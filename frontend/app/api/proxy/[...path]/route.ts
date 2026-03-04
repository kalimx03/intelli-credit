import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://54.81.253.69:8000'

export const maxDuration = 60

async function handler(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/')
  const url = `${BACKEND_URL}/${path}${request.nextUrl.search}`

  let body = undefined
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const contentType = request.headers.get('content-type') || ''
    if (contentType.includes('multipart/form-data')) {
      body = await request.formData()
    } else {
      body = await request.text()
    }
  }

  const response = await fetch(url, {
    method: request.method,
    body: body as any,
  })

  const contentType = response.headers.get('content-type') || ''

  if (contentType.includes('application/pdf') || contentType.includes('octet-stream')) {
    const buffer = await response.arrayBuffer()
    return new NextResponse(buffer, {
      status: response.status,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': response.headers.get('Content-Disposition') || 'attachment',
      },
    })
  }

  const data = await response.json()
  return NextResponse.json(data, { status: response.status })
}

export const GET = handler
export const POST = handler
