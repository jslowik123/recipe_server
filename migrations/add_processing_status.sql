-- Migration: Add processing_status column to clothes table
-- This column tracks the status of async image processing

ALTER TABLE clothes
ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';

-- Add check constraint for valid values
ALTER TABLE clothes
ADD CONSTRAINT clothes_processing_status_check
CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed'));

-- Create index for performance on status queries
CREATE INDEX IF NOT EXISTS idx_clothes_processing_status
ON clothes(processing_status);

-- Update existing rows to 'completed' (assuming they're already processed)
UPDATE clothes
SET processing_status = 'completed'
WHERE processing_status IS NULL;
