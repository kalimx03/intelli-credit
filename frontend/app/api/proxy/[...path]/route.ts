import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://54.81.253.69:8000'

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/')
  const url = `${BACKEND_URL}/${path}${request.nextUrl.search}`
  const response = await fetch(url)
  const data = await response.json()
  return NextResponse.json(data)
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/')
  const url = `${BACKEND_URL}/${path}`
  const contentType = request.headers.get('content-type') || ''
  let body
  if (contentType.includes('multipart/form-data')) {
    body = await request.formData()
  } else {
    body = await request.text()
  }
  const response = await fetch(url, {
    method: 'POST',
    body: body as any,
  })
  const data = await response.json()
  return NextResponse.json(data)
}
