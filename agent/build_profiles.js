// Build-specific native identities. Python validates the installed DLL and its
// matching IL2CPP metadata before it supplies a digest to the agent.
const nativeBuildProfile = (() => {
    const standalone214 = {
        registryObservation: true,
        hair: {
            length: {getter: '<CreateGroups>b__41', setter: '<CreateGroups>b__42', modifier: '<CreateGroups>b__97'},
            hair_count: {getter: '<CreateGroups>b__51', setter: '<CreateGroups>b__52', modifier: '<CreateGroups>b__102'},
        },
    };
    const studio216 = {
        registryObservation: true,
        hair: {
            length: {getter: '<CreateGroups>b__42', setter: '<CreateGroups>b__43', modifier: '<CreateGroups>b__98'},
            hair_count: {getter: '<CreateGroups>b__52', setter: '<CreateGroups>b__53', modifier: '<CreateGroups>b__103'},
        },
    };
    const profiles = new Map([
        ['ed65ebbc1e806db635566347a9022b9577f6b3d373db128ea23f0e862e005296', standalone214],
        ['3334b166e298682eeda1ca1c5ca568b12f7085b76cc629668fe8b192af816bd8', studio216],
        ['c8daa116938b40896e3a09208bbde71604a92d5ca6d86f9ff8b89fea3c1a5ad2', studio216],
    ]);
    return digest => profiles.get(digest);
})();
