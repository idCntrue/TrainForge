export interface Point {
  x: number
  y: number
}

export function isShapeEditable(tool: string, disabled: boolean): boolean {
  return tool === 'select' && !disabled
}

export function denormalizePoints(points: number[], width: number, height: number): number[] {
  return points.map((value, index) => value * (index % 2 === 0 ? width : height))
}

export function normalizePoints(points: number[], width: number, height: number): number[] {
  return points.map((value, index) => value / (index % 2 === 0 ? width : height))
}

export function boxFromDrag(start: Point, end: Point, width: number, height: number): number[] {
  const left = Math.min(start.x, end.x)
  const top = Math.min(start.y, end.y)
  const boxWidth = Math.abs(end.x - start.x)
  const boxHeight = Math.abs(end.y - start.y)

  return [
    (left + boxWidth / 2) / width,
    (top + boxHeight / 2) / height,
    boxWidth / width,
    boxHeight / height,
  ]
}

export function isPolygonClosingPoint(points: number[], point: Point, threshold: number): boolean {
  if (points.length < 6) return false
  return Math.hypot(point.x - points[0], point.y - points[1]) <= threshold
}

export function updatePolygonVertex(points: number[], vertexIndex: number, point: Point): number[] {
  const next = [...points]
  next[vertexIndex * 2] = point.x
  next[vertexIndex * 2 + 1] = point.y
  return next
}

export function normalizeCanvasPoint(point: Point, width: number, height: number): [number, number] {
  return [point.x / width, point.y / height]
}

export function isPointInsidePolygon(point: [number, number], polygon: number[]): boolean {
  let inside = false
  for (let current = 0, previous = polygon.length - 2; current < polygon.length; previous = current, current += 2) {
    const xi = polygon[current], yi = polygon[current + 1]
    const xj = polygon[previous], yj = polygon[previous + 1]
    if ((yi > point[1]) !== (yj > point[1]) && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}
