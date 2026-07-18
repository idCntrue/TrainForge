import { useEffect, useMemo, useRef, useState } from 'react'
import { Circle, Image as KonvaImage, Layer, Line, Rect, Stage, Text } from 'react-konva'

import type { AnnotationImageApiResponse, AnnotationShapeApiResponse, AnnotationTool } from '../../api'
import { boxFromDrag, denormalizePoints, isPolygonClosingPoint, isShapeEditable, normalizeCanvasPoint, normalizePoints, updatePolygonVertex, type Point } from './annotationGeometry'
import { shapeVisualStyle, type AnnotationObjectPresentation } from './annotationPresentation'

interface Props {
  image: AnnotationImageApiResponse
  imageUrl: string
  tool: AnnotationTool
  selectedShapeId?: string
  objects: AnnotationObjectPresentation[]
  disabled: boolean
  onSelect: (shapeId?: string) => void
  onCreate: (shapeType: 'box' | 'polygon', coordinates: number[]) => void
  onUpdate: (shape: AnnotationShapeApiResponse, coordinates: number[]) => void
  onSamPoint: (point: [number, number]) => void
  samPendingPoint?: [number, number]
  samPrompts?: Array<{ point: [number, number]; label: 0 | 1 }>
  samPreviewPolygon?: number[]
  samPreviewMode?: 'polygon' | 'pixels'
}

export default function AnnotationCanvas(props: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [canvasSize, setCanvasSize] = useState({ width: 900, height: 600 })
  const [bitmap, setBitmap] = useState<HTMLImageElement>()
  const [dragStart, setDragStart] = useState<Point>()
  const [dragEnd, setDragEnd] = useState<Point>()
  const [polygon, setPolygon] = useState<number[]>([])

  useEffect(() => {
    const node = containerRef.current
    if (!node) return
    const update = () => setCanvasSize({ width: Math.max(320, node.clientWidth), height: Math.max(260, node.clientHeight) })
    update()
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const next = new Image()
    next.onload = () => setBitmap(next)
    next.src = props.imageUrl
    return () => { next.onload = null }
  }, [props.imageUrl])

  useEffect(() => {
    setPolygon([])
    setDragStart(undefined)
    setDragEnd(undefined)
  }, [props.image.frame_id, props.tool])

  const viewport = useMemo(() => {
    const scale = Math.min(canvasSize.width / props.image.width, canvasSize.height / props.image.height)
    const width = props.image.width * scale
    const height = props.image.height * scale
    return { x: (canvasSize.width - width) / 2, y: (canvasSize.height - height) / 2, width, height }
  }, [canvasSize, props.image.height, props.image.width])

  const localPoint = (event: any): Point | undefined => {
    const point = event.target.getStage()?.getPointerPosition()
    if (!point) return undefined
    const local = { x: point.x - viewport.x, y: point.y - viewport.y }
    if (local.x < 0 || local.y < 0 || local.x > viewport.width || local.y > viewport.height) return undefined
    return local
  }

  const pointerDown = (event: any) => {
    if (props.disabled) return
    const point = localPoint(event)
    if (!point) return
    if (props.tool === 'box') {
      setDragStart(point)
      setDragEnd(point)
    } else if (props.tool === 'polygon') {
      if (isPolygonClosingPoint(polygon, point, 10)) {
        props.onCreate('polygon', normalizePoints(polygon, viewport.width, viewport.height))
        setPolygon([])
      } else {
        setPolygon((current) => [...current, point.x, point.y])
      }
    } else if (props.tool === 'sam') {
      props.onSamPoint(normalizeCanvasPoint(point, viewport.width, viewport.height))
    } else {
      props.onSelect(undefined)
    }
  }

  const pointerMove = (event: any) => {
    if (props.tool !== 'box' || !dragStart) return
    const point = localPoint(event)
    if (point) setDragEnd(point)
  }

  const pointerUp = () => {
    if (props.tool === 'box' && dragStart && dragEnd && Math.hypot(dragEnd.x - dragStart.x, dragEnd.y - dragStart.y) >= 4) {
      props.onCreate('box', boxFromDrag(dragStart, dragEnd, viewport.width, viewport.height))
    }
    setDragStart(undefined)
    setDragEnd(undefined)
  }

  return (
    <div ref={containerRef} className="annotation-canvas-host">
      <Stage width={canvasSize.width} height={canvasSize.height} onMouseDown={pointerDown} onMouseMove={pointerMove} onMouseUp={pointerUp}>
        <Layer>
          <Rect x={0} y={0} width={canvasSize.width} height={canvasSize.height} fill="#101715" />
          {bitmap && <KonvaImage image={bitmap} x={viewport.x} y={viewport.y} width={viewport.width} height={viewport.height} listening={false} />}
          {props.objects.map((object) => (
            <PersistedShape key={object.id} object={object} viewport={viewport} selected={object.id === props.selectedShapeId} editable={isShapeEditable(props.tool, props.disabled)} listening onSelect={props.onSelect} onUpdate={props.onUpdate} />
          ))}
          {dragStart && dragEnd && <Rect x={viewport.x + Math.min(dragStart.x, dragEnd.x)} y={viewport.y + Math.min(dragStart.y, dragEnd.y)} width={Math.abs(dragEnd.x - dragStart.x)} height={Math.abs(dragEnd.y - dragStart.y)} stroke="#53d6b4" strokeWidth={2} dash={[6, 4]} />}
          {polygon.length > 0 && <>
            <Line points={polygon.map((value, index) => value + (index % 2 === 0 ? viewport.x : viewport.y))} stroke="#f4c75b" strokeWidth={2} />
            {Array.from({ length: polygon.length / 2 }, (_, index) => <Circle key={index} x={viewport.x + polygon[index * 2]} y={viewport.y + polygon[index * 2 + 1]} radius={index === 0 ? 6 : 4} fill={index === 0 ? '#f4c75b' : '#fff'} />)}
          </>}
          {props.samPendingPoint && <>
            <Circle x={viewport.x + props.samPendingPoint[0] * viewport.width} y={viewport.y + props.samPendingPoint[1] * viewport.height} radius={9} fill="rgba(22,119,255,.22)" stroke="#58a6ff" strokeWidth={2} listening={false} />
            <Circle x={viewport.x + props.samPendingPoint[0] * viewport.width} y={viewport.y + props.samPendingPoint[1] * viewport.height} radius={3} fill="#fff" listening={false} />
          </>}
          {props.samPreviewPolygon && <Line points={denormalizePoints(props.samPreviewPolygon, viewport.width, viewport.height).map((value, index) => value + (index % 2 === 0 ? viewport.x : viewport.y))} closed fill={props.samPreviewMode === 'pixels' ? 'rgba(123,92,255,.38)' : 'rgba(123,92,255,.18)'} stroke="#7b5cff" strokeWidth={2} listening={false} />}
          {props.samPrompts?.map((prompt, index) => <Circle key={`${prompt.label}-${index}`} x={viewport.x + prompt.point[0] * viewport.width} y={viewport.y + prompt.point[1] * viewport.height} radius={6} fill={prompt.label === 1 ? '#22a06b' : '#e5484d'} stroke="#fff" strokeWidth={2} listening={false} />)}
        </Layer>
      </Stage>
    </div>
  )
}

function PersistedShape({ object, viewport, selected, editable, listening, onSelect, onUpdate }: { object: AnnotationObjectPresentation; viewport: { x: number; y: number; width: number; height: number }; selected: boolean; editable: boolean; listening: boolean; onSelect: (id?: string) => void; onUpdate: (shape: AnnotationShapeApiResponse, coordinates: number[]) => void }) {
  const { shape } = object
  const visual = shapeVisualStyle(object.color, selected)
  const selectShape = (event: any) => { event.cancelBubble = true; onSelect(shape.id) }
  if (shape.shape_type === 'box') {
    const [cx, cy, width, height] = shape.coordinates
    return <>
      <Rect
        x={viewport.x + (cx - width / 2) * viewport.width}
        y={viewport.y + (cy - height / 2) * viewport.height}
        width={width * viewport.width}
        height={height * viewport.height}
        stroke={visual.classStroke}
        fill={visual.fill}
        strokeWidth={visual.strokeWidth}
        listening={listening}
        draggable={editable}
        onMouseDown={selectShape}
        onClick={selectShape}
        onDragEnd={(event) => onUpdate(shape, [
          (event.target.x() - viewport.x + event.target.width() / 2) / viewport.width,
          (event.target.y() - viewport.y + event.target.height() / 2) / viewport.height,
          width,
          height,
        ])}
      />
      {selected && <Rect
        x={viewport.x + (cx - width / 2) * viewport.width - 3}
        y={viewport.y + (cy - height / 2) * viewport.height - 3}
        width={width * viewport.width + 6}
        height={height * viewport.height + 6}
        stroke={visual.selectionStroke}
        strokeWidth={2}
        dash={[7, 4]}
        listening={false}
      />}
      <ShapeLabel x={viewport.x + (cx - width / 2) * viewport.width} y={viewport.y + (cy - height / 2) * viewport.height} text={`#${object.number} ${object.label}`} color={object.color} />
    </>
  }

  const points = denormalizePoints(shape.coordinates, viewport.width, viewport.height)
  const stagePoints = points.map((value, index) => value + (index % 2 === 0 ? viewport.x : viewport.y))
  return <>
    <Line points={stagePoints} closed fill={visual.fill} stroke={visual.classStroke} strokeWidth={visual.strokeWidth} listening={listening} onMouseDown={selectShape} onClick={selectShape} />
    {selected && <Line points={stagePoints} closed stroke={visual.selectionStroke} strokeWidth={2} dash={[7, 4]} listening={false} />}
    <ShapeLabel x={Math.min(...stagePoints.filter((_, index) => index % 2 === 0))} y={Math.min(...stagePoints.filter((_, index) => index % 2 === 1))} text={`#${object.number} ${object.label}`} color={object.color} />
    {selected && editable && Array.from({ length: points.length / 2 }, (_, index) => (
      <Circle key={index} x={viewport.x + points[index * 2]} y={viewport.y + points[index * 2 + 1]} radius={6} fill="#fff" stroke={visual.selectionStroke} strokeWidth={2} draggable onMouseDown={selectShape} onDragStart={selectShape} onDragEnd={(event) => {
        event.cancelBubble = true
        const updated = updatePolygonVertex(points, index, { x: event.target.x() - viewport.x, y: event.target.y() - viewport.y })
        onUpdate(shape, normalizePoints(updated, viewport.width, viewport.height))
      }} />
    ))}
  </>
}

function ShapeLabel({ x, y, text, color }: { x: number; y: number; text: string; color: string }) {
  const width = Math.max(58, Math.min(220, text.length * 7 + 12))
  return <>
    <Rect x={x} y={Math.max(2, y - 22)} width={width} height={20} fill={color} cornerRadius={2} listening={false} />
    <Text x={x + 6} y={Math.max(5, y - 19)} width={width - 12} height={14} text={text} fill="#fff" fontSize={12} wrap="none" ellipsis listening={false} />
  </>
}
