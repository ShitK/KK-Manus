import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogTrigger,
  DialogTitle,
} from '@/components/ui/dialog';
import { useMediaQuery } from '@/hooks/use-media-query';
import Image from 'next/image';
import { useTheme } from 'next-themes';
import { Check, ExternalLink } from 'lucide-react';

interface EnterpriseModalProps {
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function KortixEnterpriseModal({ 
  children,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange
}: EnterpriseModalProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const isDesktop = useMediaQuery('(min-width: 768px)');
  const { resolvedTheme } = useTheme();
  const isDarkMode = resolvedTheme === 'dark';

  // Use controlled or internal state
  const open = controlledOpen !== undefined ? controlledOpen : internalOpen;
  const setOpen = controlledOnOpenChange || setInternalOpen;

  const benefits = [
    "Repository structure and commit history",
    "Frontend and backend architecture overview",
    "Agent runtime and sandbox reference",
    "Self-hosting setup material",
    "Project direction and roadmap context",
    "Project context kept explicit",
    "Implementation notes for local adaptation",
    "GitHub-first exploration path"
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent className="p-0 gap-0 border-none max-w-[90vw] lg:max-w-[80vw] xl:max-w-[70vw] rounded-xl overflow-hidden">
        <DialogTitle className="sr-only">
          KKManus Project Repository
        </DialogTitle>
        <div className="grid grid-cols-1 lg:grid-cols-2 h-[700px] lg:h-[800px]">
          {/* Enhanced Info Panel */}
          <div className="p-6 lg:p-8 flex flex-col bg-white dark:bg-black relative h-full overflow-y-auto border-r border-gray-200 dark:border-gray-800">
            <div className="relative z-10 flex flex-col h-full">
              <div className="mb-6 flex-shrink-0">
                <Image
                  src={isDarkMode ? '/kortix-logo-white.svg' : '/kortix-logo.svg'}
                  alt="KKManus Logo"
                  width={80}
                  height={28}
                  className="h-7 w-auto"
                />
              </div>

              <div className="mb-6 flex-shrink-0">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-primary/10 to-secondary/10 border border-primary/20 mb-4">
                  <div className="w-2 h-2 rounded-full bg-primary"></div>
                  <span className="text-xs font-medium text-primary">Project Repository</span>
                </div>
                
                <h2 className="text-2xl lg:text-3xl font-semibold tracking-tight mb-3 text-foreground">
                  Explore the KKManus Project
                </h2>
                <p className="text-base lg:text-lg text-muted-foreground mb-6 leading-relaxed">
                  Open the repository to review the implementation, architecture context, and project direction behind KKManus.
                </p>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-800 pt-6 flex-1">
                <h3 className="text-lg font-semibold mb-4 text-foreground">What's Included</h3>
                <div className="space-y-3">
                  {benefits.map((benefit, index) => (
                    <div key={index} className="flex items-start gap-3">
                      <div className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/20 flex items-center justify-center mt-0.5">
                        <Check className="w-3 h-3 text-primary" />
                      </div>
                      <p className="text-sm text-muted-foreground leading-relaxed">{benefit}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-800 pt-4 mt-6 flex-shrink-0">
                <div className="text-center space-y-2">
                  <div className="flex items-center justify-center gap-2 text-sm font-medium text-foreground">
                    <ExternalLink className="w-4 h-4 text-primary" />
                    <span>KKManus Project</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Repository reference and implementation details
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Project Link Panel */}
          <div className="bg-white dark:bg-[#171717] h-full overflow-hidden">
            <div className="h-full flex items-center justify-center p-8 text-center">
              <a
                href="https://github.com/ShitK/KK-Manus"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                View KKManus on GitHub
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Export with original name for backwards compatibility
export const KortixProcessModal = KortixEnterpriseModal;
