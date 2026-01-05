# Design Language - OFFSUIT Inspired

## Design Principles

### Minimalism
- **Less is more**: Remove all unnecessary elements
- **Whitespace**: Generous spacing for breathing room
- **Focus**: Only essential information visible

### Typography
- **Font**: System fonts (-apple-system, Inter, SF Pro Display)
- **Sizes**: 11px, 12px, 13px, 14px (limited scale)
- **Weights**: 400 (regular), 500 (medium), 600 (semibold)
- **Letter spacing**: -0.5px for headings, 0.5px for uppercase labels

### Color Palette
- **Background**: #0a0a0a (primary), #111111 (secondary), #1a1a1a (tertiary)
- **Text**: #ffffff (primary), #999999 (secondary), #666666 (tertiary)
- **Borders**: #252525 (subtle separation)
- **Accents**: #ffffff (primary), #4a9eff (success), #ff6b6b (warning)
- **Cards**: #1a1a1a background, #2a2a2a border

### Spacing
- **Base unit**: 4px
- **Common spacing**: 8px, 12px, 16px, 24px, 32px
- **Padding**: Minimal (8px-12px for inputs, 16px-24px for panels)
- **Margins**: Generous (24px-32px between sections)

### Borders & Shadows
- **Borders**: 1px solid, subtle colors (#252525)
- **Radius**: 4px-6px (minimal rounding)
- **Shadows**: None (flat design)
- **Depth**: Achieved through background color differences

### Interactions
- **Hover**: Subtle background color change
- **Transitions**: 0.2s ease (quick, responsive)
- **States**: Clear but minimal (border color changes)
- **Feedback**: Immediate but subtle

### Components

#### Buttons
- Flat design, no gradients
- Border: 1px solid
- Padding: 8px 16px
- Border radius: 4px
- Hover: Background change only

#### Inputs
- Same style as buttons
- Focus: Border color change
- No shadows or glows

#### Cards
- Minimal design
- Small size (56x78px)
- Clean typography
- Subtle hover effect

#### Seats
- Compact (100px width)
- Essential info only
- Status badges minimal
- Active state: border highlight

### Layout
- **Grid**: Clean, structured
- **Alignment**: Left-aligned text, centered cards
- **Hierarchy**: Size and color, not decoration
- **Balance**: Asymmetric but balanced

### Animations
- **Minimal**: Fade in for new events only
- **No pulse**: Removed distracting animations
- **Subtle**: Transform on hover (translateY -2px)

### Responsive
- **Breakpoints**: 1200px, 768px
- **Adaptation**: Stack layout on mobile
- **Touch targets**: Minimum 44px

## Design Tokens

```css
--bg-primary: #0a0a0a
--bg-secondary: #111111
--bg-tertiary: #1a1a1a
--border: #252525
--text-primary: #ffffff
--text-secondary: #999999
--text-tertiary: #666666
--accent: #ffffff
--success: #4a9eff
--warning: #ff6b6b
```

## Key Differences from Original

1. **Removed**: Gradients, shadows, emojis, decorative elements
2. **Simplified**: Typography scale, color palette, spacing
3. **Focused**: Essential information only
4. **Refined**: Subtle borders, minimal rounding, flat design
5. **Clean**: System fonts, consistent sizing, clear hierarchy

## Inspiration

Based on OFFSUIT's design philosophy:
- Dark, minimal interface
- Focus on cards and gameplay
- Clean typography
- Subtle interactions
- Professional, poker-focused aesthetic

