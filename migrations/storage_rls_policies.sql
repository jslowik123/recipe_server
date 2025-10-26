-- Storage RLS Policies for Wardroberry
-- Allow authenticated users to manage their own images

-- ========================================
-- clothing-images-original bucket
-- ========================================

-- Policy: Users can upload their own images
CREATE POLICY "Users can upload their own original images"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'clothing-images-original'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can read their own images
CREATE POLICY "Users can read their own original images"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'clothing-images-original'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can update their own images
CREATE POLICY "Users can update their own original images"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'clothing-images-original'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can delete their own images
CREATE POLICY "Users can delete their own original images"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'clothing-images-original'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- ========================================
-- clothing-images-processed bucket
-- ========================================

-- Policy: Users can upload their own processed images
CREATE POLICY "Users can upload their own processed images"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'clothing-images-processed'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can read their own processed images
CREATE POLICY "Users can read their own processed images"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'clothing-images-processed'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can update their own processed images
CREATE POLICY "Users can update their own processed images"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'clothing-images-processed'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can delete their own processed images
CREATE POLICY "Users can delete their own processed images"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'clothing-images-processed'
  AND (storage.foldername(name))[1] = auth.uid()::text
);
