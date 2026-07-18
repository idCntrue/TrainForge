export const IMAGE_UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024
export const GATEWAY_UPLOAD_LIMIT_BYTES = 20 * 1024 * 1024 * 1024
export const IMAGE_UPLOAD_GUIDANCE = '支持 JPG、PNG、BMP、WebP；单张不超过 50 MB，本次上传总计不超过 20 GB'

type UploadFileLike = { name: string; size: number }

export function uploadLimitError(files: UploadFileLike[], kind: 'image' | 'video' | 'archive'): string | null {
  if (kind === 'image') {
    const oversized = files.find((file) => file.size > IMAGE_UPLOAD_LIMIT_BYTES)
    if (oversized) return `${oversized.name} 超过单张图片 50 MB 的限制`
  }
  const total = files.reduce((sum, file) => sum + file.size, 0)
  if (total > GATEWAY_UPLOAD_LIMIT_BYTES) return '本次选择的文件总大小超过网关 20 GB 的请求限制，请分批上传'
  return null
}
