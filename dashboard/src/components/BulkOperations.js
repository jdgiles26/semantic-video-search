/**
 * Bulk operations panel for mission-critical workflows.
 */
import React, { useState } from 'react';
import { api } from '../hooks/useApi';

function BulkOperations({ selectedItems, onClearSelection, onOperationComplete }) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [operation, setOperation] = useState(null);
  const [progress, setProgress] = useState(0);

  const handleBulkDelete = async () => {
    if (!window.confirm(`Delete ${selectedItems.length} items?`)) return;
    
    setIsProcessing(true);
    setOperation('delete');
    setProgress(0);

    try {
      for (let i = 0; i < selectedItems.length; i++) {
        const item = selectedItems[i];
        if (item.source_type === 'upload' && item.asset_id) {
          // Delete uploaded asset
          await api.delete(`/uploads/assets/${item.asset_id}`);
        } else if (item.source_name) {
          // Delete clips by source
          await api.delete(`/clips/${item.source_name}`);
        }
        setProgress(((i + 1) / selectedItems.length) * 100);
      }
      onOperationComplete?.();
      onClearSelection();
    } catch (err) {
      console.error('Bulk delete failed:', err);
      alert('Some items failed to delete. Check console for details.');
    } finally {
      setIsProcessing(false);
      setOperation(null);
    }
  };

  const handleBulkExport = async () => {
    setIsProcessing(true);
    setOperation('export');
    setProgress(0);

    try {
      // Generate export data
      const exportData = {
        exported_at: new Date().toISOString(),
        items: selectedItems.map(item => ({
          id: item.id,
          source_type: item.source_type,
          source_name: item.source_name,
          timestamp: item.timestamp,
          score: item.score,
        })),
      };

      // Download as JSON
      const blob = new Blob([JSON.stringify(exportData, null, 2)], {
        type: 'application/json'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `export-${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      onClearSelection();
    } catch (err) {
      console.error('Bulk export failed:', err);
    } finally {
      setIsProcessing(false);
      setOperation(null);
    }
  };

  const handleBulkDispatch = async () => {
    if (selectedItems.length === 0) return;
    
    setIsProcessing(true);
    setOperation('dispatch');

    try {
      const clipIds = selectedItems.map(item => item.id).filter(Boolean);
      const result = await api.post('/alerts/dispatch', {
        query: `Bulk dispatch of ${selectedItems.length} clips`,
        clip_ids: clipIds,
        channels: ['redis'],
      });

      alert(`Dispatch completed: ${result.data.report}`);
      onClearSelection();
    } catch (err) {
      console.error('Bulk dispatch failed:', err);
      alert('Dispatch failed. Check console for details.');
    } finally {
      setIsProcessing(false);
      setOperation(null);
    }
  };

  if (selectedItems.length === 0) return null;

  return (
    <div className="bulk-operations">
      <div className="bulk-header">
        <span className="bulk-count">{selectedItems.length} selected</span>
        <button className="clear-btn" onClick={onClearSelection}>
          Clear
        </button>
      </div>

      {isProcessing ? (
        <div className="bulk-progress">
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="progress-text">
            {operation === 'delete' && 'Deleting...'}
            {operation === 'export' && 'Exporting...'}
            {operation === 'dispatch' && 'Dispatching...'}
          </span>
        </div>
      ) : (
        <div className="bulk-actions">
          <button onClick={handleBulkDispatch} className="action-btn dispatch">
            🚨 Dispatch
          </button>
          <button onClick={handleBulkExport} className="action-btn export">
            📥 Export
          </button>
          <button onClick={handleBulkDelete} className="action-btn delete">
            🗑️ Delete
          </button>
        </div>
      )}
    </div>
  );
}

export default BulkOperations;
