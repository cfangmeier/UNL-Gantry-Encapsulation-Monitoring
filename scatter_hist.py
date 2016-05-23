

def scatter_hist(xs, ys, fig, nbins=10, plot_mean=False,
                 xlabel=None, ylabel=None, aspect='equal', **kwargs):
    import numpy as np
    from matplotlib.ticker import NullFormatter

    # definitions for the axes
    left, width = 0.1, 0.65
    bottom, height = 0.1, 0.65
    bottom_h = left_h = left + width + 0.02

    rect_scatter = [left, bottom, width, height]
    rect_histx = [left, bottom_h, width, 0.2]
    rect_histy = [left_h, bottom, 0.2, height]

    axScatter = fig.add_axes(rect_scatter, adjustable='datalim', aspect=aspect)
    axHistx = fig.add_axes(rect_histx)
    axHisty = fig.add_axes(rect_histy)

    # no labels
    nullfmt = NullFormatter()
    axHistx.xaxis.set_major_formatter(nullfmt)
    axHisty.yaxis.set_major_formatter(nullfmt)

    # the scatter plot:
    axScatter.scatter(xs, ys)
    if plot_mean:
        mean_x = np.mean(xs)
        std_x = np.std(xs)
        mean_y = np.mean(ys)
        std_y = np.std(ys)
        axScatter.plot([np.mean(xs)], [np.mean(ys)], 'or')
        fmt = ("$N={}$\n"
               "$\\mu_x={:.03f}$\n$\\sigma_x={:.03f}$\n"
               "$\\mu_y={:.03f}$\n$\\sigma_y={:.03f}$")
        label = fmt.format(len(xs), mean_x, std_x, mean_y, std_y)
        fig.text(0.8, 0.78, label, fontsize=17)
    
    if xlabel:
        axScatter.set_xlabel(xlabel)
    if ylabel:
        axScatter.set_ylabel(ylabel)

    range_ = max(map(abs,axScatter.get_xlim()))*2
    binwidth = range_ / nbins
    bins = np.arange(-range_/2, range_/2 + binwidth, binwidth)
    axHistx.hist(xs, bins=bins)
    
    range_ = max(map(abs,axScatter.get_ylim()))*2
    binwidth = range_ / nbins
    bins = np.arange(-range_/2, range_/2 + binwidth, binwidth)
    axHisty.hist(ys, bins=bins, orientation='horizontal')

    #needed to keep ranges in sync
    def on_draw(*args, **kwargs):
        hist_x = axHistx.get_xlim()
        scat_x = axScatter.get_xlim()
        hist_y = axHisty.get_ylim()
        scat_y = axScatter.get_ylim()
        def neq(rng1, rng2):
            return rng1[0]!=rng2[0] or rng1[1]!=rng2[1]
        if neq(hist_x,scat_x):
            axHistx.set_xlim(axScatter.get_xlim())
        if neq(hist_y, scat_y):
            axHisty.set_ylim(axScatter.get_ylim())
        
    fig.canvas.mpl_connect('draw_event', on_draw)
    
    xMax = axHistx.get_ylim()[1]
    yMax = axHisty.get_xlim()[1]
    axHistx.set_yticks([0, xMax//3, 2*xMax//3, xMax])
    axHisty.set_xticks([0, yMax//3, 2*yMax//3, yMax])