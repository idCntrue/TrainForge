import { describe, expect, it } from 'vitest'

import {
  boxFromDrag,
  denormalizePoints,
  isPointInsidePolygon,
  isShapeEditable,
  isPolygonClosingPoint,
  normalizeCanvasPoint,
  normalizePoints,
  updatePolygonVertex,
} from './annotationGeometry'

describe('annotation geometry', () => {
  it('detects whether a SAM prompt is inside the current mask polygon', () => {
    const polygon = [0.1, 0.1, 0.9, 0.1, 0.9, 0.9, 0.1, 0.9]
    expect(isPointInsidePolygon([0.5, 0.5], polygon)).toBe(true)
    expect(isPointInsidePolygon([0.95, 0.5], polygon)).toBe(false)
  })
  it('round trips polygon coordinates through canvas pixels', () => {
    const pixels = denormalizePoints([0.1, 0.2, 0.8, 0.9], 1000, 500)
    expect(pixels).toEqual([100, 100, 800, 450])
    expect(normalizePoints(pixels, 1000, 500)).toEqual([0.1, 0.2, 0.8, 0.9])
  })

  it('creates normalized yolo box from either drag direction', () => {
    expect(boxFromDrag({ x: 80, y: 60 }, { x: 20, y: 20 }, 100, 100)).toEqual([0.5, 0.4, 0.6, 0.4])
  })

  it('closes a polygon only near its first vertex after three points', () => {
    const points = [10, 10, 80, 10, 80, 80]
    expect(isPolygonClosingPoint(points, { x: 14, y: 13 }, 6)).toBe(true)
    expect(isPolygonClosingPoint(points.slice(0, 4), { x: 10, y: 10 }, 6)).toBe(false)
    expect(isPolygonClosingPoint(points, { x: 30, y: 30 }, 6)).toBe(false)
  })

  it('updates a polygon vertex and normalizes canvas clicks', () => {
    expect(updatePolygonVertex([10, 10, 80, 10, 80, 80], 1, { x: 60, y: 30 })).toEqual([10, 10, 60, 30, 80, 80])
    expect(normalizeCanvasPoint({ x: 320, y: 240 }, 640, 480)).toEqual([0.5, 0.5])
  })

  it('edits persisted shapes only in select mode', () => {
    expect(isShapeEditable('select', false)).toBe(true)
    expect(isShapeEditable('polygon', false)).toBe(false)
    expect(isShapeEditable('select', true)).toBe(false)
  })
})
