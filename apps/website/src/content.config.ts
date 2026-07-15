import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

function documentationId({ entry, data }: { entry: string; data: Record<string, unknown> }) {
	if (typeof data.slug === 'string') return data.slug;
	return entry
		.replace(/^generated\//, '')
		.replace(/\.(?:md|mdx|markdown|mdown|mkdn|mkd|mdwn)$/, '')
		.replace(/\/index$/, '');
}

export const collections = {
	docs: defineCollection({ loader: docsLoader({ generateId: documentationId }), schema: docsSchema() }),
};
