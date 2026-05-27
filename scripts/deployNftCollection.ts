import { Address, toNano } from '@ton/core';
import { NftCollection } from '../wrappers/NftCollection';
import { compile, NetworkProvider } from '@ton/blueprint';

export async function run(provider: NetworkProvider) {
    const ownerAddress = Address.parse('0QCP28sByTvC0BmeocWsivaovvPuhzW98hnYCQt0mzcoJL8b');
    
    const nftCollection = provider.open(
        NftCollection.createFromConfig({ ownerAddress }, await compile('NftCollection'))
    );

    await nftCollection.sendDeploy(provider.sender(), toNano('0.05'));
    await provider.waitForDeploy(nftCollection.address);

    console.log('Collection deployed at:', nftCollection.address.toString());
}
