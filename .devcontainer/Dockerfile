FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# ============================================================================
# NeoVim, TMux, and Development Tools
# ============================================================================

# Install NeoVim (from source for latest version), TMux, and basic tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git jq bash ca-certificates tmux silversearcher-ag fzf ripgrep \
    build-essential cmake ninja-build gettext unzip \
    software-properties-common \
    # Node.js for Mason LSP (required for many language servers)
    nodejs npm \
    # Python development tools
    python3-dev python3-pip python3-venv \
    # Terraform
    wget gnupg \
  && rm -rf /var/lib/apt/lists/*

# Install NeoVim (nightly or latest stable)
RUN wget https://github.com/neovim/neovim/releases/download/v0.10.0/nvim-linux64.tar.gz \
    && tar -xzf nvim-linux64.tar.gz \
    && mv nvim-linux64 /opt/nvim \
    && ln -sf /opt/nvim/bin/nvim /usr/local/bin/nvim \
    && rm nvim-linux64.tar.gz

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install lefthook (Git hooks manager)
RUN curl -1sLf https://gets.lefthook.dev | bash
ENV PATH="/root/.local/bin:$PATH"

# Install AWS CLI v2
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip -q awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws

# Install Terraform
RUN wget -q https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip \
    && unzip -q terraform_1.7.0_linux_amd64.zip \
    && mv terraform /usr/local/bin/ \
    && rm terraform_1.7.0_linux_amd64.zip

# Install AWS SAM CLI
RUN pip install aws-sam-cli

# Install SageMaker Python SDK (for AWS ML deployment)
RUN pip install sagemaker

# ============================================================================
# NeoVim Configuration with Mason LSP
# ============================================================================

# Create NeoVim config directory
RUN mkdir -p /root/.config/nvim

# Install lazy.nvim (Plugin manager)
RUN curl -LO https://github.com/LazyVim/LazyVim/archive/refs/heads/main.zip \
    && unzip -q main.zip \
    && mkdir -p /root/.config/nvim \
    && mv LazyVim-main /root/.local/share/nvim/lazy/LazyVim \
    && rm main.zip

# Create init.lua with Mason LSP configuration
RUN cat > /root/.config/nvim/init.lua << 'NEOF'
-- NeoVim Configuration with Mason LSP
-- Features: Python, Terraform, AWS, SageMaker support

-- Set up package manager
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git",
    "clone",
    "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable",
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

-- Configure lazy.nvim
require("lazy").setup({
  -- Core
  { "nvim-lua/plenary.nvim" },
  { "nvim-lualine/lualine.nvim" },
  
  -- Mason LSP Manager
  {
    "williamboman/mason.nvim",
    cmd = "Mason",
    build = ":MasonUpdate",
    config = function()
      require("mason").setup({
        ui = {
          border = "rounded",
          icons = {
            package_installed = "✓",
            package_pending = "➜",
            package_uninstalled = "✗",
          },
        },
        log_level = vim.log.levels.INFO,
        max_concurrent_installers = 4,
      })
    end,
  },
  {
    "williamboman/mason-lspconfig.nvim",
    config = function()
      require("mason-lspconfig").setup({
        automatic_installation = true,
        ensure_installed = {
          -- Python
          "pyright",
          "ruff",
          "ruff_lint",
          -- Terraform
          "terraform",
          "terraformls",
          -- AWS/Cloud
          "aws-lsp",
        },
      })
    end,
  },
  
  -- LSP Config
  { "neovim/nvim-lspconfig" },
  
  -- Autocompletion
  { "hrsh7th/nvim-cmp" },
  { "hrsh7th/cmp-nvim-lsp" },
  { "hrsh7th/cmp-buffer" },
  { "hrsh7th/cmp-path" },
  
  -- Treesitter (syntax highlighting)
  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    config = function()
      require("nvim-treesitter.configs").setup({
        ensure_installed = {
          "python", "terraform", "hcl", "bash", "yaml", "json", "dockerfile"
        },
        highlight = { enable = true },
        indent = { enable = true },
      })
    end,
  },
  
  -- TMux integration (optional)
  { "christoomey/vim-tmux-navigator" },
  
  -- Terraform formatting
  { "hashivim/vim-terraform" },
})

-- LSP Configuration
local lspconfig = require("lspconfig")
local cmp = require("cmp")
local cmp_lsp = require("cmp_nvim_lsp")

-- Setup LSP servers
local capabilities = cmp_lsp.default_capabilities()

-- Python (Pyright)
lspconfig.pyright.setup({
  capabilities = capabilities,
  settings = {
    pyright = {
      python = {
        analysis = {
          typeCheckingMode = "basic",
          autoSearchPaths = true,
          useLibraryCodeForTypes = true,
        },
      },
    },
  },
})

-- Terraform
lspconfig.terraform.setup({
  capabilities = capabilities,
  settings = {
    terraform = {
      experimentalFeatures = {
        validateOnSave = true,
      },
    },
  },
})
lspconfig.terraformls.setup({ capabilities = capabilities })

-- AWS LSP
lspconfig.aws_lsp.setup({
  capabilities = capabilities,
  settings = {
    aws = {
      s3 = { enable = true },
      lambda = { enable = true },
    },
  },
})

-- Ruff (Python linter)
lspconfig.ruff.setup({
  capabilities = capabilities,
  settings = {
    ruff = {
      lint = {
        select = { "E", "F", "W", "I", "N", "UP" },
        ignore = { "E501" },
      },
    },
  },
})

-- Configure cmp
cmp.setup({
  sources = cmp.config.sources({
    { name = "nvim_lsp" },
    { name = "path" },
  }, {
    { name = "buffer" },
  }),
  mapping = cmp.mapping.preset.insert({
    ["<Tab>"] = cmp.mapping.select_next_item(),
    ["<S-Tab>"] = cmp.mapping.select_prev_item(),
    ["<CR>"] = cmp.mapping.confirm({ select = true }),
  }),
})

-- Keybindings
vim.keymap.set("n", "gd", vim.lsp.buf.definition)
vim.keymap.set("n", "gr", vim.lsp.buf.references)
vim.keymap.set("n", "K", vim.lsp.buf.hover)
vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename)

-- UI settings
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.expandtab = true
vim.opt.signcolumn = "yes"
vim.opt.cursorline = true
vim.opt.wrap = false

-- Colorscheme
vim.cmd("colorscheme default")

-- Statusline
require("lualine").setup({
  options = {
    theme = "auto",
    section_separators = "",
    component_separators = "",
  },
})

-- Mason commands
vim.api.nvim_create_user_command("MasonInstallAll", function()
  require("mason-install-all")
end, {})

-- Auto-install LSPs on startup
vim.api.nvim_create_autocmd("LspAttach", {
  callback = function(args)
    local client = vim.lsp.get_client_by_id(args.data.client_id)
    if client and client.name == "terraform" then
      vim.cmd("TerraformFormat")
    end
  end,
})

NEOF

# ============================================================================
# TMux Configuration
# ============================================================================

# Create TMux config
RUN cat > /root/.tmux.conf << 'TMOF'
# TMux Configuration for ImageML Pipeline Development

# Set prefix to Ctrl-a
set -g prefix C-a
unbind C-b
bind C-a send-prefix

# Start windows at 1
set -g base-index 1
set -g pane-base-index 1

# Mouse support
set -g mouse on

# Focus events
set -g focus-events on

# Auto-rename windows
set -g automatic-rename on
set -g allow-rename on

# Status bar
set -g status-interval 5
set -g status-left-length 30
set -g status-right-length 60

# History
set -g history-limit 10000

# Faster key repetition
set -s escape-time 0

# Reload config
bind r source-file ~/.tmux.conf

# Split panes
bind | split-window -h -c "#{pane_current_path}"
bind - split-window -v -c "#{pane_current_path}"

# Vim-like pane navigation
bind h select-pane -L
bind j select-pane -D
bind k select-pane -U
bind l select-pane -R

# Resize panes
bind -r H resize-pane -L 5
bind -r J resize-pane -D 5
bind -r K resize-pane -U 5
bind -r L resize-pane -R 5

# TPM - Plugin Manager
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'tmux-plugins/tmux-sensible'
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'

# Auto-save/resume
set -g @continuum-restore 'on'
set -g @resurrect-strategy-nvim 'session'

# Initialize TPM (keep this at the very bottom)
run '~/.tmux/plugins/tpm/tpm'
TMOF

# Install TMux plugins
RUN git clone https://github.com/tmux-plugins/tpm /root/.tmux/plugins/tpm

# ============================================================================
# Project-Specific Setup
# ============================================================================

WORKDIR /workspace

# Copy project files (will be overridden by volume mount in devcontainer.json)
COPY . /workspace/

# Install Python dependencies in project mode
RUN uv pip install --system -e pipeline_common \
    -e stage1 -e stage2 -e stage3 -e stage4

# Create convenient shell scripts for development
RUN echo '#!/bin/bash' > /usr/local/bin/dev-start && \
    echo 'tmux new-session -d -s dev "cd /workspace && nvim"' && \
    echo 'tmux split-window -h -t dev' && \
    echo 'tmux split-window -v -t dev' && \
    echo 'tmux attach -t dev' && \
    chmod +x /usr/local/bin/dev-start

# Default shell
SHELL ["/bin/bash", "-l"]
CMD ["bash"]
