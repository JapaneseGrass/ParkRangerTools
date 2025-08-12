import sharp from 'sharp';

export async function generateThumbnail(buffer: Buffer, mime: string): Promise<Buffer | null> {
  if (mime.startsWith('image/')) {
    return sharp(buffer).resize(320).withMetadata().toBuffer();
  }
  // TODO: implement video thumbnail generation
  return null;
}
