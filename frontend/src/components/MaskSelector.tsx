import { MaskType } from '../types';
import { Grid3X3, Droplets, Square, Palette, Replace, BoxSelect } from 'lucide-react';

interface MaskSelectorProps {
  selected: MaskType;
  onChange: (mask: MaskType) => void;
}

const masks = [
  { id: 'blur' as MaskType, label: 'Blur', icon: Droplets, desc: 'Gaussian blur effect' },
  { id: 'pixelate' as MaskType, label: 'Pixelate', icon: Grid3X3, desc: 'Retro pixelation' },
  { id: 'blackbox' as MaskType, label: 'Black Box', icon: Square, desc: 'Solid black overlay' },
  { id: 'redbox' as MaskType, label: 'Red Box', icon: Palette, desc: 'Red highlight overlay' },
  { id: 'whitebox' as MaskType, label: 'White Box', icon: BoxSelect, desc: 'White overlay' },
  { id: 'synthetic' as MaskType, label: 'Synthetic', icon: Replace, desc: 'AI-generated fake data' },
];

export const MaskSelector = ({ selected, onChange }: MaskSelectorProps) => {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {masks.map((mask) => {
        const Icon = mask.icon;
        const isActive = selected === mask.id;

        return (
          <button
            key={mask.id}
            onClick={() => onChange(mask.id)}
            className={`
              p-4 rounded-xl border-2 text-left transition-all duration-200
              ${isActive 
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 shadow-md' 
                : 'border-gray-200 dark:border-dark-600 hover:border-primary-300 dark:hover:border-primary-700'
              }
            `}
          >
            <Icon className={`w-6 h-6 mb-2 ${isActive ? 'text-primary-600' : 'text-gray-500'}`} />
            <p className={`font-semibold text-sm ${isActive ? 'text-primary-700 dark:text-primary-400' : 'text-gray-700 dark:text-gray-300'}`}>
              {mask.label}
            </p>
            <p className="text-xs text-gray-400 mt-1">{mask.desc}</p>
          </button>
        );
      })}
    </div>
  );
};
