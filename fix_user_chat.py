with open('iway ui/src/app/zones/user-chat/user-chat.component.ts', 'r') as f:
    content = f.read()

# 1. Update breakpoint from 768 to 1024
content = content.replace("this.isDesktopMode = window.innerWidth >= 768;", "this.isDesktopMode = window.innerWidth >= 1024; // lg breakpoint")

# 2. Update sidebar classes
content = content.replace(
    'class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 md:hidden transition-opacity"',
    'class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 lg:hidden transition-opacity"'
)

content = content.replace(
    'class="w-72 flex flex-col border-r flex-shrink-0 absolute md:relative z-50 h-full transition-transform duration-300 transform"',
    'class="w-72 flex flex-col border-r flex-shrink-0 absolute lg:relative z-50 h-full transition-transform duration-300 transform"'
)

# 3. Update burger menu button in Header
content = content.replace(
    '<button (click)="toggleSidebar()" class="md:hidden p-1.5 -ml-1 rounded-lg transition-colors cursor-pointer flex-shrink-0"',
    '<button (click)="toggleSidebar()" class="lg:hidden p-1.5 -ml-1 rounded-lg transition-colors cursor-pointer flex-shrink-0 z-50"'
)

# 4. Update logout button
content = content.replace(
    '<button (click)="logout()" class="md:hidden w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer"',
    '<button (click)="logout()" class="lg:hidden w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer"'
)

with open('iway ui/src/app/zones/user-chat/user-chat.component.ts', 'w') as f:
    f.write(content)
