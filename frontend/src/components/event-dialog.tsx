"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import {
  ApiError,
  Attachment,
  Report,
  deleteAttachment,
  getAttachmentFileUrl,
  uploadReportAttachment,
} from "@/lib/api";
import { getSymbolColor, RESCHEDULED_STYLE } from "@/lib/colors";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertTriangleIcon,
  CalendarIcon,
  ClockIcon,
  ExternalLinkIcon,
  EyeIcon,
  FileTextIcon,
  Loader2Icon,
  PanelRightCloseIcon,
  Trash2Icon,
  TrendingUpIcon,
  UploadIcon,
} from "lucide-react";

interface EventDialogProps {
  report: Report | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAttachmentsChange?: () => void | Promise<unknown>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function EventDialog({
  report,
  open,
  onOpenChange,
  onAttachmentsChange,
}: EventDialogProps) {
  const [previewAttachmentId, setPreviewAttachmentId] = useState<string | null>(
    null,
  );
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  if (!report) return null;

  const attachments = report.attachments ?? [];
  const previewAttachment: Attachment | null =
    attachments.find((att) => att.id === previewAttachmentId) ?? null;
  const isPreviewOpen = previewAttachment !== null;

  const color = getSymbolColor(report.symbol);
  const isRescheduled = Boolean(report.rescheduled_to);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setPreviewAttachmentId(null);
      setIsDragging(false);
    }
    onOpenChange(nextOpen);
  };

  const handleFiles = async (files: FileList | File[]) => {
    const fileList = Array.from(files);
    if (fileList.length === 0) return;

    const pdfs = fileList.filter(
      (f) =>
        f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"),
    );
    if (pdfs.length === 0) {
      toast.error("Only PDF files can be attached.");
      return;
    }
    if (pdfs.length < fileList.length) {
      toast.warning("Skipped non-PDF files. Uploading PDF files only.");
    }

    setIsUploading(true);
    let uploadedCount = 0;
    let lastUploaded: Attachment | null = null;
    try {
      for (const file of pdfs) {
        try {
          lastUploaded = await uploadReportAttachment(report.id, file);
          uploadedCount += 1;
        } catch (err) {
          const message =
            err instanceof ApiError ? err.message : "Failed to upload PDF";
          toast.error(`Failed to upload ${file.name}`, {
            description: message,
          });
        }
      }
      if (uploadedCount > 0) {
        await onAttachmentsChange?.();
        toast.success(
          uploadedCount === 1 && lastUploaded
            ? `Attached ${lastUploaded.filename}`
            : `Attached ${uploadedCount} PDF reports`,
        );
      }
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDelete = async (attachment: Attachment) => {
    setDeletingId(attachment.id);
    try {
      await deleteAttachment(attachment.id);
      if (previewAttachmentId === attachment.id) {
        setPreviewAttachmentId(null);
      }
      await onAttachmentsChange?.();
      toast.success(`Removed ${attachment.filename}`);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to delete attachment";
      toast.error("Could not delete attachment", { description: message });
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className={
          isPreviewOpen
            ? "sm:max-w-6xl w-[95vw] h-[88vh] p-0 gap-0 overflow-hidden border-border/40 bg-background/95 backdrop-blur-xl shadow-2xl flex flex-col lg:flex-row transition-[max-width,height] duration-200"
            : "sm:max-w-lg max-h-[85vh] overflow-y-auto overflow-x-hidden border-border/40 bg-background/95 backdrop-blur-xl p-6 shadow-2xl transition-[max-width] duration-200"
        }
      >
        {/* Left Column: Event Details & Attachments */}
        <div
          className={
            isPreviewOpen
              ? "w-full lg:w-[380px] lg:shrink-0 min-w-0 border-b lg:border-b-0 lg:border-r border-border/40 p-5 overflow-y-auto overflow-x-hidden flex flex-col gap-4 max-h-[38vh] lg:max-h-none"
              : "flex flex-col gap-4 min-w-0"
          }
        >
          <DialogHeader className="gap-1.5 pb-2 border-b border-border/40">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span
                  className="px-2.5 py-1 text-xs font-semibold rounded-md border tracking-wider"
                  style={{
                    backgroundColor: color.bg,
                    borderColor: color.border,
                    color: color.text,
                  }}
                >
                  {report.symbol}
                </span>
                {isRescheduled && (
                  <Badge
                    variant="outline"
                    className={`${RESCHEDULED_STYLE.badge} text-[11px] font-medium flex items-center gap-1`}
                  >
                    <AlertTriangleIcon className="w-3 h-3 text-amber-400" />
                    Rescheduled
                  </Badge>
                )}
              </div>
            </div>
            <DialogTitle className="text-xl font-bold tracking-tight text-foreground pt-2">
              {report.name || report.symbol}
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Earnings Release Details & Financial Reports
            </DialogDescription>
          </DialogHeader>

          {isRescheduled && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2.5">
              <AlertTriangleIcon className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="font-semibold text-amber-300">
                  Date Revision Notice
                </p>
                <p>
                  Originally scheduled for{" "}
                  <span className="font-semibold line-through text-amber-400/80">
                    {report.report_date}
                  </span>
                  . Rescheduled to{" "}
                  <span className="font-bold underline text-amber-200">
                    {report.rescheduled_to}
                  </span>
                  .
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-border/30 bg-card/50 p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <CalendarIcon className="w-3.5 h-3.5 text-muted-foreground" />
                <span>Earnings Date</span>
              </div>
              <p className="text-sm font-semibold text-foreground">
                {report.report_date}
              </p>
            </div>

            <div className="rounded-lg border border-border/30 bg-card/50 p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <ClockIcon className="w-3.5 h-3.5 text-muted-foreground" />
                <span>Fiscal Period End</span>
              </div>
              <p className="text-sm font-semibold text-foreground">
                {report.fiscal_date_ending}
              </p>
            </div>

            <div className="col-span-2 rounded-lg border border-border/30 bg-card/50 p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <TrendingUpIcon className="w-3.5 h-3.5 text-muted-foreground" />
                <span>Consensus EPS Estimate</span>
              </div>
              <p className="text-base font-semibold text-foreground">
                {report.estimate ? (
                  <>
                    <span className="text-emerald-400 font-mono">
                      {report.currency === "USD" ? "$" : ""}
                      {report.estimate}
                    </span>{" "}
                    <span className="text-xs text-muted-foreground font-normal">
                      {report.currency}
                    </span>
                  </>
                ) : (
                  <span className="text-muted-foreground font-normal text-sm">
                    Not disclosed / consensus pending
                  </span>
                )}
              </p>
            </div>
          </div>

          {/* Attachments Section */}
          <div className="space-y-2.5 pt-2 border-t border-border/40 min-w-0">
            <div className="flex items-center justify-between gap-2 min-w-0">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <FileTextIcon className="w-3.5 h-3.5" />
                Financial Reports ({attachments.length})
              </h3>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isUploading}
                onClick={() => fileInputRef.current?.click()}
                className="h-7 px-2.5 text-xs"
              >
                {isUploading ? (
                  <>
                    <Loader2Icon className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <UploadIcon className="w-3.5 h-3.5 mr-1.5" />
                    Attach PDF
                  </>
                )}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) {
                    void handleFiles(e.target.files);
                  }
                }}
              />
            </div>

            {/* Drag-and-drop area */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                if (e.dataTransfer.files?.length) {
                  void handleFiles(e.dataTransfer.files);
                }
              }}
              className={`min-w-0 overflow-hidden rounded-lg border border-dashed transition-colors ${
                isDragging
                  ? "border-blue-400 bg-blue-500/10"
                  : "border-border/40 bg-card/30"
              } ${attachments.length === 0 ? "p-4 text-center" : "p-2"}`}
            >
              {attachments.length === 0 ? (
                <button
                  type="button"
                  disabled={isUploading}
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full flex flex-col items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <UploadIcon className="w-4 h-4 opacity-70" />
                  <span>Drop PDF reports here or click to browse</span>
                  <span className="text-[11px] opacity-60">
                    Press release, 10-Q/10-K, or earnings deck (up to 50 MB)
                  </span>
                </button>
              ) : (
                <ul className="space-y-1.5 min-w-0">
                  {attachments.map((att) => {
                    const isActive = previewAttachment?.id === att.id;
                    const isDeleting = deletingId === att.id;
                    return (
                      <li
                        key={att.id}
                        className={`flex items-center justify-between gap-2 min-w-0 overflow-hidden rounded-md border px-2.5 py-2 text-xs transition-colors ${
                          isActive
                            ? "border-blue-500/60 bg-blue-500/10"
                            : "border-border/30 bg-background/50 hover:bg-accent/40"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() =>
                            setPreviewAttachmentId(isActive ? null : att.id)
                          }
                          className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden text-left cursor-pointer"
                          title={att.filename}
                        >
                          <FileTextIcon
                            className={`w-4 h-4 shrink-0 ${
                              isActive
                                ? "text-blue-400"
                                : "text-muted-foreground"
                            }`}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="font-medium text-foreground truncate">
                              {att.filename}
                            </p>
                            <p className="text-[11px] text-muted-foreground">
                              {formatBytes(att.size_bytes)} •{" "}
                              {new Date(att.uploaded_at).toLocaleDateString()}
                            </p>
                          </div>
                        </button>

                        <div className="flex items-center gap-1 shrink-0">
                          <Button
                            type="button"
                            variant={isActive ? "secondary" : "ghost"}
                            size="icon-sm"
                            onClick={() =>
                              setPreviewAttachmentId(isActive ? null : att.id)
                            }
                            title={isActive ? "Close preview" : "Preview PDF"}
                            className="h-7 w-7"
                          >
                            <EyeIcon className="w-3.5 h-3.5" />
                            <span className="sr-only">
                              {isActive ? "Close preview" : "Preview PDF"}
                            </span>
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            disabled={isDeleting}
                            onClick={() => void handleDelete(att)}
                            title={`Delete ${att.filename}`}
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                          >
                            {isDeleting ? (
                              <Loader2Icon className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Trash2Icon className="w-3.5 h-3.5" />
                            )}
                            <span className="sr-only">Delete PDF</span>
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Inline PDF Preview Pane */}
        {previewAttachment && (
          <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-zinc-950/90">
            <div className="flex items-center justify-between gap-2 px-4 py-2.5 pr-12 border-b border-border/40 bg-card/40 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <FileTextIcon className="w-4 h-4 text-blue-400 shrink-0" />
                <span className="text-sm font-medium text-foreground truncate">
                  {previewAttachment.filename}
                </span>
                <span className="text-xs text-muted-foreground shrink-0 hidden sm:inline">
                  ({formatBytes(previewAttachment.size_bytes)})
                </span>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  asChild
                  className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                >
                  <a
                    href={getAttachmentFileUrl(previewAttachment.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLinkIcon className="w-3.5 h-3.5 mr-1" />
                    <span className="hidden sm:inline">New Tab</span>
                  </a>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setPreviewAttachmentId(null)}
                  className="h-7 px-2 text-xs"
                >
                  <PanelRightCloseIcon className="w-3.5 h-3.5 mr-1" />
                  <span className="hidden sm:inline">Hide Preview</span>
                </Button>
              </div>
            </div>

            <iframe
              key={previewAttachment.id}
              src={getAttachmentFileUrl(previewAttachment.id)}
              title={previewAttachment.filename}
              className="w-full flex-1 border-0 bg-zinc-900"
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
